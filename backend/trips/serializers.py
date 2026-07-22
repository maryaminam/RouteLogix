import zoneinfo
from functools import lru_cache

from django.conf import settings
from rest_framework import serializers
from .models import Trip, LogSheet


@lru_cache(maxsize=1)
def _available_timezones() -> frozenset:
    """
    Every IANA zone name this host knows.

    Cached because available_timezones() walks the whole tz database each call,
    which is far too much work to repeat per request just to validate a string.
    The set is fixed for the life of the process — a tzdata upgrade ships in a
    new release anyway.
    """
    return frozenset(zoneinfo.available_timezones())


class TripRequestSerializer(serializers.Serializer):
    """Validates the incoming trip-planning request."""

    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used_hours = serializers.FloatField(min_value=0, max_value=70)
    # § 395.8 requires every log time to be recorded in the home terminal's time
    # zone. The browser's detected zone stands in for it — see README.
    home_terminal_timezone = serializers.CharField(max_length=64)

    def validate_home_terminal_timezone(self, value):
        """
        Rejects anything ZoneInfo can't resolve.

        The name reaches us from the browser and is fed straight to
        ZoneInfo(), which raises ZoneInfoNotFoundError on an unknown key — an
        unhandled 500 rather than a 400 telling the caller what was wrong. It
        also decides which local midnight splits the log into days, so a
        plausible-looking but wrong zone would silently shift every sheet.
        """
        name = value.strip()
        if name not in _available_timezones():
            raise serializers.ValidationError(
                f"{name!r} is not a recognised IANA time zone name "
                f"(expected something like 'America/Chicago')."
            )
        return name


class LogSheetSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogSheet
        fields = [
            "day_number",
            "date",
            "segments",
            "total_off_duty_hours",
            "total_sleeper_berth_hours",
            "total_driving_hours",
            "total_on_duty_hours",
        ]


class TripSerializer(serializers.ModelSerializer):
    logs = LogSheetSerializer(many=True, read_only=True)
    cycle_summary = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "id",
            "current_location",
            "pickup_location",
            "dropoff_location",
            "current_cycle_used_hours",
            "distance_miles",
            "duration_hours",
            "route_geometry",
            "stops",
            "created_at",
            "logs",
            "cycle_summary",
        ]
        read_only_fields = fields

    def get_cycle_summary(self, obj):
        summary = getattr(obj, "planning_summary", None)
        if summary is not None:
            return summary

        max_cycle_hours = settings.HOS_RULESET["MAX_CYCLE_HOURS"]
        cycle_used = float(obj.current_cycle_used_hours)
        restart_count = 0
        cycle_hours_used_during_trip = 0.0

        for log in obj.logs.all().order_by("day_number"):
            for segment in log.segments:
                label = segment.get("label", "")
                status = segment.get("status")
                hours = float(segment.get("hours", 0))

                if label == "34-hour restart":
                    cycle_used = 0.0
                    restart_count += 1
                    continue

                if status in {"DRIVING", "ON_DUTY"}:
                    cycle_used += hours
                    cycle_hours_used_during_trip += hours

        return {
            "current_cycle_used_hours": round(float(obj.current_cycle_used_hours), 2),
            "remaining_cycle_hours_before_trip": round(max(0, max_cycle_hours - float(obj.current_cycle_used_hours)), 2),
            "cycle_hours_used_during_trip": round(cycle_hours_used_during_trip, 2),
            "cycle_after_trip_hours": round(cycle_used, 2),
            "remaining_cycle_hours_after_trip": round(max(0, max_cycle_hours - cycle_used), 2),
            "restart_required": restart_count > 0,
            "restart_count": restart_count,
            "reset_status": settings.HOS_RULESET.get("RESET_STATUS", "SLEEPER_BERTH"),
        }
