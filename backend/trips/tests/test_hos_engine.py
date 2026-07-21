from datetime import datetime
from django.test import SimpleTestCase
from django.conf import settings

from trips.services.hos_engine import plan_trip
from trips.services.hos_engine import HOSEngine
from trips.services.daily_split import split_into_days


class HOSEngineTests(SimpleTestCase):
    def setUp(self):
        self.ruleset = settings.HOS_RULESET
        self.start = datetime(2026, 1, 1, 6, 0)

    def test_short_trip_single_day_no_reset(self):
        # 4 hours of driving, fresh cycle -> should fit in one day, no resets.
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              total_driving_hours=4, distance_miles=220)
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
                              total_driving_hours=9, distance_miles=495)
        breaks = [s for s in segments if "break" in s.label.lower()]
        self.assertTrue(any(abs(b.hours - 0.5) < 1e-3 for b in breaks))

    def test_11_hour_driving_limit_forces_reset(self):
        # 15 hours of total driving requested -> must hit the 11-hr cap and reset.
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              total_driving_hours=15, distance_miles=825)
        driving_day_one = 0
        reset_seen = False
        for s in segments:
            if s.status == "DRIVING" and not reset_seen:
                driving_day_one += s.hours
            if s.status == "OFF_DUTY" and s.hours >= 10:
                reset_seen = True
        self.assertTrue(reset_seen)
        self.assertLessEqual(driving_day_one, 11 + 1e-6)

    def test_reset_period_uses_sleeper_berth_by_default(self):
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              total_driving_hours=15, distance_miles=825)
        reset_segments = [s for s in segments if s.label == "10-hour reset"]
        self.assertTrue(reset_segments)
        self.assertTrue(all(s.status == "SLEEPER_BERTH" for s in reset_segments))

    def test_total_driving_hours_conserved(self):
        total_requested = 20
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              total_driving_hours=total_requested, distance_miles=1100)
        total_driving = sum(s.hours for s in segments if s.status == "DRIVING")
        self.assertAlmostEqual(total_driving, total_requested, places=2)

    def test_cycle_limit_triggers_34_hour_restart(self):
        # Start already at 68 of 70 hours used -> should hit cycle limit almost immediately
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=68,
                              total_driving_hours=10, distance_miles=550)
        long_resets = [s.hours for s in segments if s.status == "SLEEPER_BERTH" and s.hours >= 34]
        self.assertTrue(long_resets, "Expected a 34-hour restart when cycle limit is nearly exhausted")

    def test_cycle_summary_reports_remaining_cycle_and_restart_flag(self):
        engine = HOSEngine(self.ruleset, self.start, cycle_used_hours=10)
        engine.plan(total_driving_hours=4, distance_miles=220)

        summary = engine.get_summary()
        self.assertEqual(summary["current_cycle_used_hours"], 10)
        self.assertEqual(summary["remaining_cycle_hours_before_trip"], 60)
        self.assertFalse(summary["restart_required"])
        self.assertEqual(summary["cycle_after_trip_hours"], 16)
        self.assertEqual(summary["remaining_cycle_hours_after_trip"], 54)

    def test_daily_split_totals_24_hours_per_day_except_last(self):
        segments = plan_trip(self.ruleset, self.start, cycle_used_hours=0,
                              total_driving_hours=15, distance_miles=825)
        days = split_into_days(segments)
        self.assertGreaterEqual(len(days), 2)
        for day in days[:-1]:
            total = sum(day["totals"].values())
            self.assertAlmostEqual(total, 24, places=1)
