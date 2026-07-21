from django.conf import settings
from rest_framework import serializers
from .models import Trip, LogSheet


class TripRequestSerializer(serializers.Serializer):
    """Validates the incoming trip-planning request."""

    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used_hours = serializers.FloatField(min_value=0, max_value=70)


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
