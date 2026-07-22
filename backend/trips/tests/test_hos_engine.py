from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.conf import settings

from trips.services.hos_engine import plan_trip, advance, elapsed_hours
from trips.services.hos_engine import HOSEngine
from trips.services.daily_split import split_into_days, _clock
from trips.services.route_locations import RouteLocator
from trips.services.routing import cumulative_distances, split_geometry_by_waypoints
from trips.serializers import TripRequestSerializer

# The suite runs on a real home terminal zone rather than naive datetimes, so
# the day-splitting and duty arithmetic are exercised the way production uses
# them. Chicago observes DST, which is what makes the transitions below testable.
HOME_TZ = ZoneInfo("America/Chicago")


def at(year, month, day, hour=0, minute=0, tz=HOME_TZ):
    """A wall-clock moment at the home terminal."""
    return datetime(year, month, day, hour, minute, tzinfo=tz)


def route_legs(total_driving_hours, distance_miles, pickup_at=0.1):
    """
    Splits a trip into the two legs HOSEngine.plan() expects, with the pickup
    `pickup_at` of the way along.

    Trip-wide totals are preserved, so tests asserting on overall driving time
    or cycle usage are unaffected by where the pickup falls.
    """
    return [
        {
            "distance_miles": distance_miles * pickup_at,
            "duration_hours": total_driving_hours * pickup_at,
        },
        {
            "distance_miles": distance_miles * (1 - pickup_at),
            "duration_hours": total_driving_hours * (1 - pickup_at),
        },
    ]


def driving_hours_per_duty_window(segments, ruleset):
    """
    Driving hours in each duty window, where a window is the stretch between
    two qualifying resets.

    Only an off-duty/sleeper block of REQUIRED_OFF_DUTY_HOURS or more closes a
    window — the 30-minute break does not, which is exactly the distinction the
    11-hour limit turns on.
    """
    reset_hours = ruleset["REQUIRED_OFF_DUTY_HOURS"]
    windows = []
    driving = 0.0

    for segment in segments:
        if segment.status in {"OFF_DUTY", "SLEEPER_BERTH"} and segment.hours >= reset_hours:
            windows.append(driving)
            driving = 0.0
        elif segment.status == "DRIVING":
            driving += segment.hours

    windows.append(driving)
    return windows


def miles_between(a, b):
    """Great-circle distance in miles between two [lat, lng] points."""
    return cumulative_distances([a, b])[-1]


def densify(start, end, steps):
    """A straight polyline from `start` to `end` with `steps` evenly spaced hops."""
    return [
        [
            start[0] + (end[0] - start[0]) * index / steps,
            start[1] + (end[1] - start[1]) * index / steps,
        ]
        for index in range(steps + 1)
    ]


class HOSEngineTests(SimpleTestCase):
    def setUp(self):
        self.ruleset = settings.HOS_RULESET
        self.start = at(2026, 1, 1, 6, 0)

    def test_short_trip_single_day_no_reset(self):
        # 4 hours of driving, fresh cycle -> should fit in one day, no resets.
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(4, 220))
        statuses = [s.status for s in segments]
        self.assertIn("DRIVING", statuses)
        self.assertNotIn("SLEEPER_BERTH", statuses)
        total_driving = sum(s.hours for s in segments if s.status == "DRIVING")
        self.assertAlmostEqual(total_driving, 4, places=2)
        # No 10-hour reset should have been needed
        off_duty_blocks = [s.hours for s in segments if s.status == "OFF_DUTY" and s.hours >= 10]
        self.assertEqual(off_duty_blocks, [])

    def test_30_minute_break_after_8_driving_hours(self):
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(9, 495))
        breaks = [s for s in segments if "break" in s.label.lower()]
        self.assertTrue(any(abs(b.hours - 0.5) < 1e-3 for b in breaks))

    def test_11_hour_driving_limit_forces_sleeper_berth_reset(self):
        # 15 hours of total driving requested -> must hit the 11-hr cap and reset.
        # The reset is taken in the sleeper berth (RESET_STATUS), not off duty.
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(15, 825))
        driving_day_one = 0
        reset_seen = False
        for s in segments:
            if s.status == "DRIVING" and not reset_seen:
                driving_day_one += s.hours
            if s.status == "SLEEPER_BERTH" and s.hours >= 10:
                reset_seen = True
        self.assertTrue(reset_seen)
        self.assertLessEqual(driving_day_one, 11 + 1e-6)

    def test_reset_period_uses_sleeper_berth_by_default(self):
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(15, 825))
        reset_segments = [s for s in segments if s.label == "10-hour reset"]
        self.assertTrue(reset_segments)
        self.assertTrue(all(s.status == "SLEEPER_BERTH" for s in reset_segments))

    def test_total_driving_hours_conserved(self):
        total_requested = 20
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(total_requested, 1100))
        total_driving = sum(s.hours for s in segments if s.status == "DRIVING")
        self.assertAlmostEqual(total_driving, total_requested, places=2)

    def test_cycle_limit_triggers_34_hour_restart(self):
        # Start already at 68 of 70 hours used -> should hit cycle limit almost immediately
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=68,
                              legs=route_legs(10, 550))
        long_resets = [s.hours for s in segments if s.status == "SLEEPER_BERTH" and s.hours >= 34]
        self.assertTrue(long_resets, "Expected a 34-hour restart when cycle limit is nearly exhausted")

    def test_cycle_summary_reports_remaining_cycle_and_restart_flag(self):
        engine = HOSEngine(self.ruleset, self.start, cycle_used_hours=10)
        engine.plan(legs=route_legs(4, 220))

        summary = engine.get_summary()
        self.assertEqual(summary["current_cycle_used_hours"], 10)
        self.assertEqual(summary["remaining_cycle_hours_before_trip"], 60)
        self.assertFalse(summary["restart_required"])
        self.assertEqual(summary["cycle_after_trip_hours"], 16)
        self.assertEqual(summary["remaining_cycle_hours_after_trip"], 54)

    def test_daily_split_totals_24_hours_per_day_except_last(self):
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(15, 825))
        days = split_into_days(segments)
        self.assertGreaterEqual(len(days), 2)
        for day in days[:-1]:
            total = sum(day["totals"].values())
            self.assertAlmostEqual(total, 24, places=1)

    def test_calendar_day_may_exceed_11_driving_hours_across_two_duty_windows(self):
        """
        A calendar day is not a duty window.

        The 11-hour limit is per duty period, not per date. When a 10-hour reset
        lands mid-day it closes one window and opens another, so a single log
        sheet can legitimately total more than 11 hours of driving while every
        individual window stays capped. Asserted here so the oversized daily
        total on the log sheet reads as intended behaviour rather than a leak in
        the driving cap.
        """
        max_driving = self.ruleset["MAX_DRIVING_HOURS"]

        # Starting at midnight packs the most driving into day 1: a full window,
        # a full reset, and the start of the next window all land on one date.
        segments = plan_trip(self.ruleset, at(2026, 3, 2, 0, 0),
                             cycle_used_hours=0, legs=route_legs(26, 1430))
        days = split_into_days(segments)

        over_limit_days = [d for d in days if d["totals"]["DRIVING"] > max_driving]
        self.assertTrue(
            over_limit_days,
            "Scenario never produced a calendar day above 11 driving hours, so it "
            "isn't exercising the two-window case this test exists to pin down.",
        )

        # Each oversized day must owe its extra hours to a reset splitting it,
        # not to a window that simply overran.
        for day in over_limit_days:
            self.assertTrue(
                any(s["label"].endswith(("reset", "restart")) for s in day["segments"]),
                f"Day {day['day_number']} exceeded {max_driving}h of driving with no "
                f"reset to divide it into two duty windows.",
            )

        # The actual invariant: no duty window ever exceeds the driving cap.
        windows = driving_hours_per_duty_window(segments, self.ruleset)
        self.assertLessEqual(
            max(windows), max_driving + 1e-6,
            f"A duty window drove {max(windows):.2f}h, over the {max_driving}h limit. "
            f"Per-window totals were {[round(w, 2) for w in windows]}.",
        )
        # ...and it genuinely binds here, rather than passing because the legs
        # happened to be short.
        self.assertAlmostEqual(max(windows), max_driving, places=6)

        # A day can hold at most one full reset, so 24 - 10 is the ceiling on
        # how far a calendar-day total can outrun the per-window cap.
        day_ceiling = 24 - self.ruleset["REQUIRED_OFF_DUTY_HOURS"]
        for day in days:
            self.assertLessEqual(day["totals"]["DRIVING"], day_ceiling + 1e-6)

    def test_nearly_exhausted_cycle_completes_instead_of_spinning(self):
        """
        A cycle balance a hair under the limit used to wedge the simulation.

        `cycle_used` is repeatedly advanced by `MAX_CYCLE_HOURS - cycle_used`,
        which in floating point can settle a few ULPs short of 70. The engine
        then found no driving time available (0 hours to the cycle limit) but
        also refused to restart the cycle, because 69.999999999 >= 70 is false.
        Its infinite-loop guard responded with a 10-hour reset, which changes
        neither quantity — so it looped, emitting rests until the datetime
        overflowed past year 9999. In production that pins a worker at 100% CPU
        until gunicorn times it out.
        """
        segments = plan_trip(self.ruleset, self.start,
                             cycle_used_hours=70 - 1e-9, legs=route_legs(10, 550))

        restarts = [s for s in segments if s.hours >= self.ruleset["RESTART_HOURS"] - 1e-9]
        self.assertTrue(restarts, "An exhausted cycle must be cleared by a 34-hour restart")
        self.assertAlmostEqual(
            sum(s.hours for s in segments if s.status == "DRIVING"), 10, places=2)

    def test_fuel_stop_survives_a_leg_ending_on_the_fuel_interval(self):
        """
        The pickup landing exactly on a fuel boundary used to cancel the stop.

        Mileage-to-next-fuel was derived as `miles_driven % FUEL_INTERVAL`, and
        the stop was only taken when driving remained *in the current leg*. When
        leg one ended on the boundary both conditions fired at once: the stop was
        suppressed for having no driving left, and the remainder reset to zero,
        so the next boundary was pushed out a further full interval. A 1,500-mile
        trip came out with no fuel stop at all.
        """
        interval = self.ruleset["FUEL_INTERVAL_MILES"]
        total_miles = 1.5 * interval
        legs = route_legs(total_miles / 55, total_miles,
                          pickup_at=interval / total_miles)
        self.assertAlmostEqual(legs[0]["distance_miles"], interval, places=6)

        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0, legs=legs)

        self.assertEqual(
            sum(1 for s in segments if s.label == "Fuel stop"), 1,
            "A 1,500-mile trip needs a fuel stop even when the pickup falls on "
            "the 1,000-mile mark.",
        )

    def test_no_stretch_of_the_trip_runs_past_the_fuel_interval(self):
        interval = self.ruleset["FUEL_INTERVAL_MILES"]

        for total_miles in (900, 1000, 1500, 2000, 2500, 3300):
            for pickup_at in (0.05, interval / total_miles if total_miles > interval else 0.5, 0.5, 0.9):
                if not 0 < pickup_at < 1:
                    continue
                legs = route_legs(total_miles / 55, total_miles, pickup_at=pickup_at)
                segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0, legs=legs)

                miles_before_leg = [0.0, legs[0]["distance_miles"]]
                marks = [0.0]
                marks += [miles_before_leg[s.leg_index] + s.miles_into_leg
                          for s in segments if s.label == "Fuel stop"]
                marks.append(total_miles)

                worst = max(b - a for a, b in zip(marks, marks[1:]))
                self.assertLessEqual(
                    worst, interval + 1e-3,
                    f"{total_miles}mi trip with pickup at {pickup_at:.3f} drove "
                    f"{worst:.1f}mi between fuel stops.",
                )

    def test_hour_long_pickup_satisfies_the_30_minute_break(self):
        """
        § 395.3(a)(3)(ii): the break may be taken on duty, and routine work
        interruptions count so long as they are consecutive. An hour spent
        loading is one. The engine used to only credit the break it inserted
        itself, so it bolted a redundant one on shortly after every pickup.
        """
        # 7.5h to the shipper, then 3h to the consignee: 10.5h driving inside a
        # 12.5h window, so nothing but the pickup can clear the break counter.
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                             legs=route_legs(10.5, 577.5, pickup_at=7.5 / 10.5))

        self.assertEqual(
            [s.label for s in segments if "break" in s.label.lower()], [],
            "The hour-long pickup already interrupted driving; no separate "
            "30-minute break should be scheduled.",
        )
        # Still a legal plan: the break rule is satisfied, not skipped.
        driving_runs = []
        run = 0.0
        for s in segments:
            if s.status == "DRIVING":
                run += s.hours
            elif s.hours >= self.ruleset["REQUIRED_BREAK_MINUTES"] / 60:
                driving_runs.append(run)
                run = 0.0
        driving_runs.append(run)
        self.assertLessEqual(max(driving_runs), self.ruleset["DRIVING_BREAK_TRIGGER_HOURS"] + 1e-6)

    def test_log_sheets_contain_no_zero_length_status_changes(self):
        """
        A duty status is drawn and totalled to the minute. A segment shorter
        than that renders as a zero-width mark on the grid and adds a remark
        naming a town the driver never stopped in.
        """
        interval = self.ruleset["FUEL_INTERVAL_MILES"]
        # Ending a whisker past a fuel stop is what produces the sliver.
        total_miles = interval + 0.001
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                             legs=route_legs(total_miles / 55, total_miles))

        for day in split_into_days(segments):
            for entry in day["segments"]:
                self.assertGreater(
                    entry["hours"], 0,
                    f"Day {day['day_number']} logs a {entry['label']!r} of "
                    f"{entry['hours']}h at {entry['start']}.",
                )

    def test_pickup_happens_after_driving_to_the_shipper(self):
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              legs=route_legs(6, 330))
        labels = [s.label for s in segments]
        self.assertEqual(labels[0], "Driving", "Trip should open by deadheading to the shipper")
        self.assertLess(labels.index("Driving"), labels.index("Pickup"))
        self.assertEqual(labels[-1], "Drop-off")


class HomeTerminalTimezoneTests(SimpleTestCase):
    """
    § 395.8(d): every time on a log is recorded in the home terminal's zone,
    whatever zones the driver crosses. That decides where each 24-hour sheet
    begins, so the planner has to simulate on home terminal wall time.

    US DST transitions used below (2026): clocks spring forward on Sunday
    8 March and fall back on Sunday 1 November, both at 02:00 local.
    """

    def setUp(self):
        self.ruleset = settings.HOS_RULESET

    def test_log_days_break_at_home_terminal_midnight_not_utc(self):
        # 20:00 in Chicago is already 02:00 the next day in UTC. Splitting on
        # UTC midnight would date this sheet a day late and cut it in the
        # middle of the driver's evening.
        start = at(2026, 1, 5, 20, 0)
        days = split_into_days(
            plan_trip(self.ruleset, start, cycle_used_hours=0, legs=route_legs(4, 220))
        )

        self.assertEqual(days[0]["date"], start.date())
        first = days[0]["segments"][0]
        self.assertEqual(first["start"], "00:00")
        self.assertEqual(first["status"], "OFF_DUTY")
        # ...and the day's activity starts on the driver's clock, not UTC's.
        first_activity = next(s for s in days[0]["segments"] if s["status"] != "OFF_DUTY")
        self.assertEqual(first_activity["start"], "20:00")

    def test_segments_stay_in_the_home_terminal_zone(self):
        start = at(2026, 6, 1, 9, 0)
        for segment in plan_trip(self.ruleset, start, cycle_used_hours=0,
                                 legs=route_legs(15, 825)):
            self.assertEqual(segment.start.tzinfo, HOME_TZ)
            self.assertEqual(segment.end.tzinfo, HOME_TZ)

    def test_rest_across_spring_forward_is_ten_real_hours(self):
        """
        Adding a timedelta to a zone-aware datetime moves the wall clock, not
        the instant. Ten hours added across the spring-forward would leave the
        driver nine real hours of rest while the log still read ten — a short
        rest that looks compliant on paper.
        """
        before_transition = at(2026, 3, 7, 22, 0)
        rest_end = advance(before_transition, 10)

        self.assertAlmostEqual(elapsed_hours(before_transition, rest_end), 10, places=9)
        # The wall clock must show 11 hours passing, because one was skipped.
        self.assertEqual(rest_end.hour, 9)
        self.assertEqual(rest_end.utcoffset(), timedelta(hours=-5))  # now CDT
        # Plain subtraction is what this guards against: both operands share the
        # one cached ZoneInfo instance, so Python compares wall clocks and calls
        # a legal ten-hour rest eleven hours.
        self.assertEqual((rest_end - before_transition).total_seconds() / 3600, 11)

    def test_rest_across_fall_back_is_ten_real_hours(self):
        before_transition = at(2026, 10, 31, 22, 0)
        rest_end = advance(before_transition, 10)

        self.assertAlmostEqual(elapsed_hours(before_transition, rest_end), 10, places=9)
        # An hour repeats, so ten real hours only advance the clock to 07:00.
        self.assertEqual(rest_end.hour, 7)
        self.assertEqual(rest_end.utcoffset(), timedelta(hours=-6))  # back to CST
        # The dangerous direction: naive subtraction reports 9 hours, so a
        # qualifying rest stops counting as one and two duty windows merge.
        self.assertEqual((rest_end - before_transition).total_seconds() / 3600, 9)

    def test_every_duty_period_stays_legal_across_a_dst_transition(self):
        """The limits are on elapsed time, so a clock change must not relax them."""
        for label, start in (("spring forward", at(2026, 3, 7, 6, 0)),
                             ("fall back", at(2026, 10, 31, 6, 0))):
            segments = plan_trip(self.ruleset, start, cycle_used_hours=0,
                                 legs=route_legs(30, 1650))

            windows = driving_hours_per_duty_window(segments, self.ruleset)
            self.assertLessEqual(
                max(windows), self.ruleset["MAX_DRIVING_HOURS"] + 1e-6,
                f"{label}: a duty window drove {max(windows):.3f}h",
            )
            for segment in segments:
                if segment.label.endswith("reset"):
                    self.assertGreaterEqual(
                        segment.hours, self.ruleset["REQUIRED_OFF_DUTY_HOURS"] - 1e-6,
                        f"{label}: a reset was only {segment.hours:.3f} real hours",
                    )

    def test_dst_day_totals_23_or_25_hours(self):
        """
        A calendar day containing a clock change is genuinely 23 or 25 hours
        long, and the log sheet for it should say so rather than being padded
        to a fictional 24.
        """
        for start, transition_date, expected in (
            (at(2026, 3, 7, 6, 0), datetime(2026, 3, 8).date(), 23),
            (at(2026, 10, 31, 6, 0), datetime(2026, 11, 1).date(), 25),
        ):
            days = split_into_days(
                plan_trip(self.ruleset, start, cycle_used_hours=0, legs=route_legs(40, 2200))
            )
            day = next((d for d in days if d["date"] == transition_date), None)
            self.assertIsNotNone(day, f"No log sheet covering {transition_date}")
            self.assertAlmostEqual(sum(day["totals"].values()), expected, places=1)

        # Ordinary days are unaffected.
        days = split_into_days(
            plan_trip(self.ruleset, at(2026, 6, 1, 6, 0), 0, route_legs(40, 2200))
        )
        for day in days[:-1]:
            self.assertAlmostEqual(sum(day["totals"].values()), 24, places=1)

    def test_duty_spanning_the_repeated_hour_keeps_its_time(self):
        """
        On the day the clocks go back, 01:00-02:00 local happens twice. A duty
        period inside it starts and ends on the same clock reading — an
        hour-long pickup running 01:16 CDT to 01:16 CST. Treating equal
        readings as zero-length deleted the hour from the sheet, so the day
        totalled 24 instead of 25 and the driver's cycle was understated.
        """
        # 34 hours of restart from this start lands the pickup inside the
        # repeated hour on 1 November.
        segments = plan_trip(self.ruleset, at(2026, 10, 30, 13, 0),
                             cycle_used_hours=68,
                             legs=route_legs(2500 / 55, 2500, pickup_at=0.05))
        pickup = next(s for s in segments if s.label == "Pickup")
        self.assertEqual(_clock(pickup.start), _clock(pickup.end),
                         "This scenario is meant to straddle the repeated hour")
        self.assertAlmostEqual(pickup.hours, 1, places=6)

        day = next(d for d in split_into_days(segments)
                   if d["date"] == datetime(2026, 11, 1).date())
        logged = next((e for e in day["segments"] if e["label"] == "Pickup"), None)
        self.assertIsNotNone(logged, "The pickup vanished from the log sheet")
        self.assertAlmostEqual(logged["hours"], 1, places=2)
        self.assertAlmostEqual(sum(day["totals"].values()), 25, places=1)

    def test_naive_datetimes_still_plan(self):
        """The engine stays usable without a zone, which the unit tests rely on."""
        segments = plan_trip(self.ruleset, datetime(2026, 1, 1, 6, 0),
                             cycle_used_hours=0, legs=route_legs(15, 825))
        self.assertTrue(split_into_days(segments))
        self.assertIsNone(segments[0].start.tzinfo)


class TimezoneValidationTests(SimpleTestCase):
    def _payload(self, **overrides):
        return {
            "current_location": "Denver, CO",
            "pickup_location": "Omaha, NE",
            "dropoff_location": "Chicago, IL",
            "current_cycle_used_hours": 10,
            "home_terminal_timezone": "America/Chicago",
            **overrides,
        }

    def test_accepts_a_real_iana_zone(self):
        serializer = TripRequestSerializer(data=self._payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["home_terminal_timezone"], "America/Chicago")

    def test_rejects_unknown_or_malformed_zones(self):
        # "CST" and a UTC offset are the shapes a caller is most likely to send
        # by mistake; ZoneInfo would raise on each, which without validation
        # surfaces as a 500 rather than a field error.
        for bad in ("Mars/Olympus_Mons", "CST", "UTC+5", "", "   "):
            serializer = TripRequestSerializer(data=self._payload(home_terminal_timezone=bad))
            self.assertFalse(serializer.is_valid(), f"{bad!r} should be rejected")
            self.assertIn("home_terminal_timezone", serializer.errors)

    def test_timezone_is_required(self):
        payload = self._payload()
        del payload["home_terminal_timezone"]
        serializer = TripRequestSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("home_terminal_timezone", serializer.errors)


class RemarkLocationTests(SimpleTestCase):
    """
    The log-sheet remarks are only useful if the interpolated position of a
    status change actually matches where it happened. The pickup is the case
    that used to be wrong: it was booked at mile zero, so its remark named the
    driver's starting city instead of the shipper's.
    """

    def setUp(self):
        self.ruleset = settings.HOS_RULESET
        self.start = at(2026, 1, 1, 6, 0)

        # Denver -> Omaha -> Chicago, far enough apart that naming the wrong one
        # is unmistakable.
        self.current = [39.74, -104.99]
        self.pickup = [41.25, -95.93]
        self.dropoff = [41.88, -87.63]

        geometry = densify(self.current, self.pickup, 50) + densify(self.pickup, self.dropoff, 50)[1:]
        leg_geometries = split_geometry_by_waypoints(
            geometry, [self.current, self.pickup, self.dropoff]
        )

        # Road distance runs longer than the straight-line polyline it is drawn
        # as. Overstating it here is deliberate: it is exactly the discrepancy
        # that made trip-wide interpolation drift off the waypoints.
        winding_factor = 1.15
        self.legs = []
        for leg_geometry in leg_geometries:
            miles = cumulative_distances(leg_geometry)[-1] * winding_factor
            self.legs.append({
                "distance_miles": miles,
                "duration_hours": miles / self.ruleset["AVERAGE_DRIVING_SPEED_MPH"],
                "geometry": leg_geometry,
            })

        self.locator = RouteLocator(self.legs)
        self.segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0, legs=self.legs)

    def _position_of(self, label):
        segment = next(s for s in self.segments if s.label == label)
        return self.locator.position(segment.leg_index, segment.miles_into_leg)

    def test_pickup_resolves_to_the_pickup_location(self):
        position = self._position_of("Pickup")

        self.assertLess(
            miles_between(position, self.pickup), 1,
            f"Pickup interpolated to {position}, expected the shipper at {self.pickup}",
        )
        # The bug this guards against put the pickup back at the origin.
        self.assertGreater(miles_between(position, self.current), 100)

    def test_dropoff_resolves_to_the_dropoff_location(self):
        position = self._position_of("Drop-off")

        self.assertLess(miles_between(position, self.dropoff), 1)
        self.assertGreater(miles_between(position, self.pickup), 100)

    def test_driving_before_pickup_stays_on_the_first_leg(self):
        first_drive = next(s for s in self.segments if s.status == "DRIVING")
        self.assertEqual(first_drive.leg_index, 0)
        self.assertAlmostEqual(first_drive.miles_into_leg, 0, places=6)
        self.assertLess(miles_between(self._position_of("Driving"), self.current), 1)
