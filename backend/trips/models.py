from django.db import models


class Trip(models.Model):
    """A single trip-planning request and its resolved route metadata."""

    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used_hours = models.FloatField(
        help_text="Hours already used in the driver's 70hr/8day cycle before this trip."
    )

    distance_miles = models.FloatField(null=True, blank=True)
    duration_hours = models.FloatField(null=True, blank=True)
    route_geometry = models.JSONField(null=True, blank=True)
    stops = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Trip #{self.pk}: {self.pickup_location} -> {self.dropoff_location}"


class LogSheet(models.Model):
    """One 24-hour FMCSA daily log sheet belonging to a Trip."""

    trip = models.ForeignKey(Trip, related_name="logs", on_delete=models.CASCADE)
    day_number = models.PositiveIntegerField()
    date = models.DateField()

    # List of {"status": "OFF_DUTY"|"SLEEPER_BERTH"|"DRIVING"|"ON_DUTY",
    #          "start": "HH:MM", "end": "HH:MM", "location": "City, ST", "remark": str}
    segments = models.JSONField(default=list)

    total_off_duty_hours = models.FloatField(default=0)
    total_sleeper_berth_hours = models.FloatField(default=0)
    total_driving_hours = models.FloatField(default=0)
    total_on_duty_hours = models.FloatField(default=0)

    class Meta:
        ordering = ["trip", "day_number"]
        unique_together = ("trip", "day_number")

    def __str__(self):
        return f"Log day {self.day_number} for Trip #{self.trip_id}"
