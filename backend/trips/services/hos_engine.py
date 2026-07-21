"""
Hours-of-Service simulation engine.

Given a trip's total driving distance/time and the driver's current 70hr/8day
cycle usage, this module simulates the trip forward in time, applying:
  - 11-hour driving limit
  - 14-hour on-duty window
  - 30-minute break after 8 cumulative driving hours
  - 10 consecutive hours off duty to reset the daily clocks
  - 70-hour/8-day cycle limit (34-hour restart when it must reset)
  - 1 hour on-duty for pickup, 1 hour on-duty for drop-off
  - A fuel stop every FUEL_INTERVAL_MILES

It returns an ordered list of duty "segments" with absolute start/end
datetimes, which the caller then splits at midnight into daily LogSheets.

This module intentionally has NO Django/DB/HTTP dependencies so it can be
unit tested in isolation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Segment:
    status: str  # "OFF_DUTY" | "SLEEPER_BERTH" | "DRIVING" | "ON_DUTY"
    start: datetime
    end: datetime
    label: str = ""  # e.g. "Driving", "Fuel stop", "Pickup", "30-min break"
    # Where the driver was when this segment began, expressed as a route leg
    # plus how far into that leg they had travelled. We have no live GPS feed,
    # so this is what lets the caller estimate the location of a status change.
    # It is kept per-leg rather than as one trip-wide mileage so that the
    # pickup and drop-off land exactly on their waypoints instead of drifting
    # by the difference between road distance and polyline distance.
    leg_index: int = 0
    miles_into_leg: float = 0.0

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass
class DriverClock:
    """Tracks all the rolling HOS counters as we simulate forward."""

    driving_today: float = 0.0          # resets on any 10hr+ off-duty period
    duty_window_start: datetime = None   # resets on any 10hr+ off-duty period
    driving_since_break: float = 0.0     # resets on 30-min break OR off-duty
    cycle_used: float = 0.0              # resets to 0 on a 34hr+ restart


class HOSEngine:
    def __init__(self, ruleset: dict, start_time: datetime, cycle_used_hours: float):
        self.r = ruleset
        self.segments: list[Segment] = []
        self.starting_cycle_used = cycle_used_hours
        self.restart_count = 0
        self.clock = DriverClock(duty_window_start=start_time, cycle_used=cycle_used_hours)
        self.now = start_time

        # Position along the route: which leg we're on, and how far into it.
        self.leg_index = 0
        self.miles_into_leg = 0.0
        self._miles_before_leg = 0.0  # total mileage of all legs already completed
        self.miles_per_driving_hour = ruleset["AVERAGE_DRIVING_SPEED_MPH"]  # per-leg, set in _drive()

    # -- internal helpers ----------------------------------------------------

    @property
    def miles_driven(self) -> float:
        """Total miles driven across the whole trip so far, spanning all legs."""
        return self._miles_before_leg + self.miles_into_leg

    def _add(self, status: str, hours: float, label: str = ""):
        if hours <= 0:
            return
        start = self.now
        end = start + timedelta(hours=hours)
        self.segments.append(
            Segment(status, start, end, label, self.leg_index, self.miles_into_leg)
        )
        self.now = end

        if status == "DRIVING":
            self.clock.driving_today += hours
            self.clock.driving_since_break += hours
            self.clock.cycle_used += hours
            self.miles_into_leg += hours * self.miles_per_driving_hour
        elif status == "ON_DUTY":
            self.clock.cycle_used += hours
        # OFF_DUTY / SLEEPER_BERTH accrue no driving/duty hours

    def _take_reset(self, hours: float, restart_cycle: bool):
        status = self.r.get("RESET_STATUS", "SLEEPER_BERTH")
        label = "34-hour restart" if restart_cycle else f"{hours:g}-hour reset"
        self._add(status, hours, label=label)
        self.clock.driving_today = 0
        self.clock.driving_since_break = 0
        self.clock.duty_window_start = self.now
        if restart_cycle:
            self.clock.cycle_used = 0
            self.restart_count += 1

    def _duty_window_elapsed(self) -> float:
        return (self.now - self.clock.duty_window_start).total_seconds() / 3600

    def _drive_leg(self, leg: dict):
        """
        Drives one route leg to completion, stopping for every HOS interrupt
        that comes due along the way.

        The duty clocks are *not* touched at leg boundaries: the pickup between
        the two legs is on-duty time, not a reset, so the 11-hour limit, the
        14-hour window, the 30-minute break trigger and the fuel interval all
        carry straight over from the previous leg.
        """
        r = self.r
        driving_remaining = leg["duration_hours"]

        # Convert driving time to route mileage using this leg's own average
        # speed rather than the ruleset's nominal one, so that mileage markers
        # line up with the real geometry instead of drifting from it.
        self.miles_per_driving_hour = (
            leg["distance_miles"] / driving_remaining
            if driving_remaining > 0
            else r["AVERAGE_DRIVING_SPEED_MPH"]
        )

        while driving_remaining > 1e-6:
            # Hard stop: cycle limit reached -> must restart (34 consecutive hrs off)
            if self.clock.cycle_used >= r["MAX_CYCLE_HOURS"]:
                self._take_reset(r["RESTART_HOURS"], restart_cycle=True)
                continue

            # Daily driving or duty-window limit reached -> 10hr off-duty reset
            if (
                self.clock.driving_today >= r["MAX_DRIVING_HOURS"]
                or self._duty_window_elapsed() >= r["MAX_DUTY_WINDOW_HOURS"]
            ):
                self._take_reset(r["REQUIRED_OFF_DUTY_HOURS"], restart_cycle=False)
                continue

            # 30-minute break required after 8 cumulative driving hours
            if self.clock.driving_since_break >= r["DRIVING_BREAK_TRIGGER_HOURS"]:
                self._add(
                    "OFF_DUTY",
                    r["REQUIRED_BREAK_MINUTES"] / 60,
                    label="Required 30-minute break",
                )
                self.clock.driving_since_break = 0
                continue

            # Fuel stop every FUEL_INTERVAL_MILES
            next_fuel_at = r["FUEL_INTERVAL_MILES"] - (self.miles_driven % r["FUEL_INTERVAL_MILES"])
            miles_to_next_fuel = next_fuel_at if next_fuel_at > 0 else r["FUEL_INTERVAL_MILES"]

            # How much driving time is available before hitting each constraint?
            hrs_to_driving_limit = r["MAX_DRIVING_HOURS"] - self.clock.driving_today
            hrs_to_window_limit = r["MAX_DUTY_WINDOW_HOURS"] - self._duty_window_elapsed()
            hrs_to_break = r["DRIVING_BREAK_TRIGGER_HOURS"] - self.clock.driving_since_break
            hrs_to_cycle_limit = r["MAX_CYCLE_HOURS"] - self.clock.cycle_used
            hrs_to_fuel = miles_to_next_fuel / self.miles_per_driving_hour
            hrs_to_finish = driving_remaining

            drive_chunk = min(
                hrs_to_driving_limit,
                hrs_to_window_limit,
                hrs_to_break,
                hrs_to_cycle_limit,
                hrs_to_fuel,
                hrs_to_finish,
            )
            drive_chunk = max(drive_chunk, 0)

            if drive_chunk <= 1e-6:
                # Safety valve against infinite loops if two constraints tie at 0
                self._take_reset(r["REQUIRED_OFF_DUTY_HOURS"], restart_cycle=False)
                continue

            self._add("DRIVING", drive_chunk, label="Driving")
            driving_remaining -= drive_chunk

            # If we just hit the fuel threshold exactly, take the fuel stop
            if abs((self.miles_driven % r["FUEL_INTERVAL_MILES"])) < 1e-3 and driving_remaining > 1e-6:
                self._add("ON_DUTY", r["FUEL_STOP_DURATION_HOURS"], label="Fuel stop")

    def _advance_to_next_leg(self, leg: dict):
        """Moves the position marker onto the start of the following leg."""
        self._miles_before_leg += leg["distance_miles"]
        self.miles_into_leg = 0.0
        self.leg_index += 1

    # -- public API ------------------------------------------------------

    def plan(self, legs: list[dict]) -> list[Segment]:
        """
        Simulates the trip over the two route legs returned by
        routing.get_route(): current -> pickup, then pickup -> dropoff.

        Each leg is {"distance_miles": float, "duration_hours": float}.
        """
        if len(legs) != 2:
            raise ValueError(
                f"Expected 2 route legs (current->pickup, pickup->dropoff), got {len(legs)}."
            )

        r = self.r
        current_to_pickup, pickup_to_dropoff = legs

        # 1. Deadhead out to the shipper.
        self._drive_leg(current_to_pickup)

        # 2. Pickup — 1 hour on-duty, not driving. Advancing the leg first puts
        #    this segment at the pickup waypoint rather than back at mile zero.
        self._advance_to_next_leg(current_to_pickup)
        self._add("ON_DUTY", r["PICKUP_DURATION_HOURS"], label="Pickup")

        # 3. Run the load to the consignee.
        self._drive_leg(pickup_to_dropoff)

        # 4. Drop-off — 1 hour on-duty. We stay on the final leg, whose mileage
        #    is now fully consumed, so this lands on the dropoff waypoint.
        self._add("ON_DUTY", r["DROPOFF_DURATION_HOURS"], label="Drop-off")

        return self.segments

    def get_summary(self) -> dict:
        max_cycle_hours = self.r["MAX_CYCLE_HOURS"]
        total_cycle_hours_used = sum(
            segment.hours for segment in self.segments if segment.status in {"DRIVING", "ON_DUTY"}
        )
        cycle_after_trip = self.clock.cycle_used

        return {
            "current_cycle_used_hours": round(self.starting_cycle_used, 2),
            "remaining_cycle_hours_before_trip": round(max(0, max_cycle_hours - self.starting_cycle_used), 2),
            "cycle_hours_used_during_trip": round(total_cycle_hours_used, 2),
            "cycle_after_trip_hours": round(cycle_after_trip, 2),
            "remaining_cycle_hours_after_trip": round(max(0, max_cycle_hours - cycle_after_trip), 2),
            "restart_required": self.restart_count > 0,
            "restart_count": self.restart_count,
            "reset_status": self.r.get("RESET_STATUS", "SLEEPER_BERTH"),
        }


def plan_trip(ruleset: dict, start_time: datetime, cycle_used_hours: float,
              legs: list[dict]) -> list[Segment]:
    """Convenience entrypoint used by the API view."""
    engine = HOSEngine(ruleset, start_time, cycle_used_hours)
    return engine.plan(legs)
