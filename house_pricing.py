#!/usr/bin/env python3
"""Vacation house pricing calculator — OOP structure.

Designed with future UI in mind:
  - House / Room / Guest are pure data models (JSON-serializable)
  - PricingConfig holds all financial knobs
  - PricingCalculator is stateless and reusable
  - PricingResult holds computed output, ready to render anywhere
"""

from __future__ import annotations
import argparse
import json
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data Models  (map 1-to-1 with JSON — easy to bind to a UI)
# ---------------------------------------------------------------------------

@dataclass
class Guest:
    name: str
    days: int  # how many days this guest is present

    @staticmethod
    def from_dict(d: dict) -> Guest:
        return Guest(name=d["name"], days=d["days"])


@dataclass
class Room:
    name: str
    private_bathroom: bool
    is_multiple_beds: bool
    guests: list[Guest] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> Room:
        return Room(
            name=d["name"],
            private_bathroom=d.get("private_bathroom", False),
            is_multiple_beds=d.get("is_multiple_beds", False),
            guests=[Guest.from_dict(g) for g in d.get("guests", [])],
        )


@dataclass
class House:
    name: str
    total_days: int
    rooms: list[Room] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict) -> House:
        meta = data.get("house", {})
        return House(
            name=meta.get("name", "Vacation House"),
            total_days=meta["total_days"],
            rooms=[Room.from_dict(r) for r in data.get("rooms", [])],
        )


@dataclass
class PricingConfig:
    total_cost: float
    equal_split_pct: float        # % of cost split equally by guest-days
    private_bath_increase: float  # % weight increase per room for private bath
    multiple_beds_decrease: float # % weight decrease per room for multiple beds

    @staticmethod
    def from_dict(d: dict) -> PricingConfig:
        return PricingConfig(
            total_cost=d["total_cost"],
            equal_split_pct=d["equal_split_pct"],
            private_bath_increase=d["private_bath_increase"],
            multiple_beds_decrease=d["multiple_beds_decrease"],
        )


# ---------------------------------------------------------------------------
# Result Models  (output — ready to render in a UI or print to terminal)
# ---------------------------------------------------------------------------

@dataclass
class GuestResult:
    guest: Guest
    room: Room
    equal_share: float   # their share of the equal portion
    room_share: float    # their share of the room's weighted cost
    total: float         # equal_share + room_share


@dataclass
class RoomResult:
    room: Room
    weight: float
    room_cost: float     # this room's share of the room portion
    guest_results: list[GuestResult] = field(default_factory=list)


@dataclass
class PricingResult:
    house: House
    config: PricingConfig
    equal_portion: float
    room_portion: float
    room_results: list[RoomResult]

    @property
    def all_guest_results(self) -> list[GuestResult]:
        return [gr for rr in self.room_results for gr in rr.guest_results]

    @property
    def grand_total(self) -> float:
        return sum(gr.total for gr in self.all_guest_results)


# ---------------------------------------------------------------------------
# Calculator  (stateless — same inputs always produce same outputs)
# ---------------------------------------------------------------------------

class PricingCalculator:
    def __init__(self, house: House, config: PricingConfig):
        self.house = house
        self.config = config

    def calculate(self) -> PricingResult:
        cfg = self.config
        rooms = self.house.rooms

        equal_portion = cfg.total_cost * (cfg.equal_split_pct / 100)
        room_portion = cfg.total_cost - equal_portion

        # Total guest-days across the whole house (for equal split proration)
        total_guest_days = sum(
            g.days for room in rooms for g in room.guests
        )

        # --- Room weights & costs ---
        room_results: list[RoomResult] = []
        for room in rooms:
            weight = 1.0
            if room.private_bathroom:
                weight += cfg.private_bath_increase / 100
            if room.is_multiple_beds:
                weight -= cfg.multiple_beds_decrease / 100
            room_results.append(RoomResult(room=room, weight=weight, room_cost=0.0))

        total_weight = sum(rr.weight for rr in room_results)
        for rr in room_results:
            rr.room_cost = (rr.weight / total_weight) * room_portion

        # --- Per-guest costs (prorated by days) ---
        for rr in room_results:
            room_guest_days = sum(g.days for g in rr.room.guests)

            for guest in rr.room.guests:
                # Equal share: proportional to this guest's days vs all guest-days
                equal_share = (guest.days / total_guest_days) * equal_portion if total_guest_days else 0

                # Room share: proportional to this guest's days within the room
                room_share = (guest.days / room_guest_days) * rr.room_cost if room_guest_days else 0

                rr.guest_results.append(GuestResult(
                    guest=guest,
                    room=rr.room,
                    equal_share=equal_share,
                    room_share=room_share,
                    total=equal_share + room_share,
                ))

        return PricingResult(
            house=self.house,
            config=cfg,
            equal_portion=equal_portion,
            room_portion=room_portion,
            room_results=room_results,
        )


# ---------------------------------------------------------------------------
# Reporter  (presentation only — swap this out for a UI renderer later)
# ---------------------------------------------------------------------------

class PricingReporter:
    def __init__(self, result: PricingResult):
        self.r = result

    def print(self) -> None:
        r, cfg = self.r, self.r.config

        print(f"\n{'=' * 62}")
        print(f"  {r.house.name}  —  {r.house.total_days} days")
        print(f"{'=' * 62}")
        print(f"  Total Cost:             ${cfg.total_cost:>10,.2f}")
        print(f"  Equal Portion ({cfg.equal_split_pct:.0f}%):    ${r.equal_portion:>10,.2f}  (split by guest-days)")
        print(f"  Room Portion  ({100-cfg.equal_split_pct:.0f}%):    ${r.room_portion:>10,.2f}  (weighted by amenities)")
        print(f"  Private Bath Increase:  {cfg.private_bath_increase:>9.0f}%")
        print(f"  Multiple Beds Decrease: {cfg.multiple_beds_decrease:>9.0f}%")
        print(f"{'=' * 62}\n")

        # Room breakdown
        print(f"  {'Room':<18} {'Amenities':<22} {'Weight':>6} {'Room Cost':>10}")
        print(f"  {'-'*18} {'-'*22} {'-'*6} {'-'*10}")
        for rr in r.room_results:
            amenities = []
            if rr.room.private_bathroom:
                amenities.append("private bath")
            if rr.room.is_multiple_beds:
                amenities.append("multiple beds")
            label = ", ".join(amenities) if amenities else "standard"
            print(f"  {rr.room.name:<18} {label:<22} {rr.weight:>6.2f} ${rr.room_cost:>9,.2f}")
        print(f"  {'-'*18} {'-'*22} {'-'*6} {'-'*10}")
        print(f"  {'TOTAL':<47} ${r.room_portion:>9,.2f}\n")

        # Guest breakdown
        print(f"  {'Guest':<16} {'Room':<18} {'Days':>4} {'Equal':>10} {'Room':>10} {'Total':>10}")
        print(f"  {'-'*16} {'-'*18} {'-'*4} {'-'*10} {'-'*10} {'-'*10}")
        for gr in r.all_guest_results:
            print(
                f"  {gr.guest.name:<16} {gr.room.name:<18} {gr.guest.days:>4}"
                f"  ${gr.equal_share:>8,.2f}  ${gr.room_share:>8,.2f}  ${gr.total:>8,.2f}"
            )
        print(f"  {'-'*16} {'-'*18} {'-'*4} {'-'*10} {'-'*10} {'-'*10}")
        print(f"  {'GRAND TOTAL':<50} ${r.grand_total:>8,.2f}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Vacation house pricing calculator")
    parser.add_argument("input", help="Path to JSON file")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    house = House.from_dict(data)
    config = PricingConfig.from_dict(data["pricing"])

    result = PricingCalculator(house, config).calculate()
    PricingReporter(result).print()


if __name__ == "__main__":
    main()
