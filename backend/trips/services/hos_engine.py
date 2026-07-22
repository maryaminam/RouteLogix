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
from datetime import datetime, timedelta, timezone

# Every limit below is compared with a tolerance rather than exactly. The
# simulation repeatedly does `counter += limit - counter`, which in binary
# floating point can land a few ULPs *short* of the limit. Comparing exactly
# meant "have I hit the 70-hour cycle?" could answer no at 69.999999999, so the
# engine would neither restart the cycle nor be able to drive — and would spin
# taking 10-hour rests forever. These tolerances are far below the resolution of
# anything a log sheet records (a minute), so they cannot mask a real violation.
TIME_EPSILON_HOURS = 1e-6      # 3.6 milliseconds
DISTANCE_EPSILON_MILES = 1e-3  # 5 feet

# Guards against any future no-progress branch turning into a hung request.
# A legitimate plan needs a handful of iterations per driving day; a cross
# country trip on a nearly exhausted cycle stays comfortably under a thousand.
MAX_SIMULATION_STEPS = 100_000


class HOSPlanningError(Exception):
    """The simulation could not make forward progress — always a bug here."""


def advance(moment: datetime, hours: float) -> datetime:
    """
    Moves `moment` forward by a real elapsed duration.

    Adding a timedelta to a zone-aware datetime adjusts its *wall clock* fields
    and leaves the zone attached, so the result is re-interpreted at whatever
    UTC offset then applies. Across a spring-forward that turns a 10-hour rest
    into 9 real hours of sleep — an illegal short rest that the log would
    nonetheless display as compliant. Every duration the engine deals in is a
    real elapsed one, so the arithmetic is done in UTC and converted back.

    Naive datetimes have no offset to shift and are handled directly, which is
    what keeps the engine usable without a timezone.
    """
    if moment.tzinfo is None:
        return moment + timedelta(hours=hours)
    shifted = moment.astimezone(timezone.utc) + timedelta(hours=hours)
    return shifted.astimezone(moment.tzinfo)


def elapsed_hours(start: datetime, end: datetime) -> float:
    """
    Real hours between two moments.

    Subtracting datetimes that share a tzinfo object gives the difference in
    *wall clock* fields, with the offset deliberately ignored — and ZoneInfo
    hands out one cached instance per zone name, so every datetime the engine
    produces shares one. Plain subtraction therefore reports a rest spanning the
    spring-forward as 11 hours when the driver slept 10, and one spanning the
    fall-back as 9 when they slept 10. Both directions corrupt HOS accounting,
    the second by hiding a qualifying rest. Converting to UTC removes the
    offset from the comparison.
    """
    if start.tzinfo is not None and end.tzinfo is not None:
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
    return (end - start).total_seconds() / 3600


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
        return elapsed_hours(self.start, self.end)


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

        # Distance since the tank was last filled. Tracked as its own running
        # counter rather than derived from `miles_driven % FUEL_INTERVAL_MILES`:
        # the modulo silently skipped a stop whenever a leg happened to end on a
        # fuel boundary, because the remainder reset to zero at the same moment
        # the "take the stop" branch was suppressed for having no driving left.
        self.miles_since_fuel = 0.0

    # -- internal helpers ----------------------------------------------------

    @property
    def miles_driven(self) -> float:
        """Total miles driven across the whole trip so far, spanning all legs."""
        return self._miles_before_leg + self.miles_into_leg

    def _add(self, status: str, hours: float, label: str = ""):
        if hours <= 0:
            return
        start = self.now
        end = advance(start, hours)
        self.segments.append(
            Segment(status, start, end, label, self.leg_index, self.miles_into_leg)
        )
        self.now = end

        if status == "DRIVING":
            self.clock.driving_today += hours
            self.clock.driving_since_break += hours
            self.clock.cycle_used += hours
            miles = hours * self.miles_per_driving_hour
            self.miles_into_leg += miles
            self.miles_since_fuel += miles
            return

        if status == "ON_DUTY":
            self.clock.cycle_used += hours
        # OFF_DUTY / SLEEPER_BERTH accrue no driving/duty hours.

        # § 395.3(a)(3)(ii) lets the 30-minute break be taken on duty, off duty
        # or in the sleeper berth, and says ordinary interruptions to driving —
        # fuelling, loading, paperwork — satisfy it provided they are
        # consecutive. So any single non-driving block long enough counts, not
        # just the break we insert deliberately. Without this the engine bolted
        # a redundant 30-minute break onto the far side of an hour-long pickup.
        if hours >= self.r["REQUIRED_BREAK_MINUTES"] / 60 - TIME_EPSILON_HOURS:
            self.clock.driving_since_break = 0

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
        return elapsed_hours(self.clock.duty_window_start, self.now)

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

        # Each branch below either clears the constraint that blocked driving or
        # drives, so every iteration makes progress. The counter only catches a
        # future edit that breaks that property, and turns what used to be a hung
        # worker into an exception.
        for _ in range(MAX_SIMULATION_STEPS):
            if driving_remaining <= TIME_EPSILON_HOURS:
                return

            # Hard stop: cycle limit reached -> must restart (34 consecutive hrs off)
            if self.clock.cycle_used >= r["MAX_CYCLE_HOURS"] - TIME_EPSILON_HOURS:
                self._take_reset(r["RESTART_HOURS"], restart_cycle=True)
                continue

            # Daily driving or duty-window limit reached -> 10hr off-duty reset
            if (
                self.clock.driving_today >= r["MAX_DRIVING_HOURS"] - TIME_EPSILON_HOURS
                or self._duty_window_elapsed() >= r["MAX_DUTY_WINDOW_HOURS"] - TIME_EPSILON_HOURS
            ):
                self._take_reset(r["REQUIRED_OFF_DUTY_HOURS"], restart_cycle=False)
                continue

            # 30-minute break required after 8 cumulative driving hours
            if self.clock.driving_since_break >= r["DRIVING_BREAK_TRIGGER_HOURS"] - TIME_EPSILON_HOURS:
                self._add(
                    "OFF_DUTY",
                    r["REQUIRED_BREAK_MINUTES"] / 60,
                    label="Required 30-minute break",
                )
                continue

            # Fuel stop every FUEL_INTERVAL_MILES. Taken at the top of the loop
            # rather than after driving, so a stop that comes due exactly at a
            # leg boundary is honoured on entering the next leg instead of being
            # dropped: the driver still has to fill up before carrying on.
            if self.miles_since_fuel >= r["FUEL_INTERVAL_MILES"] - DISTANCE_EPSILON_MILES:
                self._add("ON_DUTY", r["FUEL_STOP_DURATION_HOURS"], label="Fuel stop")
                self.miles_since_fuel = 0.0
                continue

            # How much driving time is available before hitting each constraint?
            # Every one of these is strictly positive: the guards above have
            # already dealt with each constraint that could be at zero.
            miles_to_next_fuel = r["FUEL_INTERVAL_MILES"] - self.miles_since_fuel
            drive_chunk = min(
                r["MAX_DRIVING_HOURS"] - self.clock.driving_today,
                r["MAX_DUTY_WINDOW_HOURS"] - self._duty_window_elapsed(),
                r["DRIVING_BREAK_TRIGGER_HOURS"] - self.clock.driving_since_break,
                r["MAX_CYCLE_HOURS"] - self.clock.cycle_used,
                miles_to_next_fuel / self.miles_per_driving_hour,
                driving_remaining,
            )

            self._add("DRIVING", drive_chunk, label="Driving")
            driving_remaining -= drive_chunk

        raise HOSPlanningError(
            f"HOS simulation failed to finish a leg within {MAX_SIMULATION_STEPS} "
            f"steps ({driving_remaining:.6f}h of driving still unplanned)."
        )

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
