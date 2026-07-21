from django.contrib import admin
from .models import Trip, LogSheet


class LogSheetInline(admin.TabularInline):
    model = LogSheet
    extra = 0


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("id", "pickup_location", "dropoff_location", "distance_miles", "created_at")
    inlines = [LogSheetInline]
