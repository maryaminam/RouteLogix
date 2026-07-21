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
        ]
        read_only_fields = fields
