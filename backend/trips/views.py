from datetime import datetime

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import TripRequestSerializer, TripSerializer
from .models import Trip, LogSheet
from .services.geocoding import geocode, GeocodingError
from .services.routing import get_route, RoutingError
from .services.hos_engine import HOSEngine
from .services.daily_split import split_into_days


class TripPlanView(APIView):
    """
    POST /api/trips/plan/

    Body: {
        "current_location": str,
        "pickup_location": str,
        "dropoff_location": str,
        "current_cycle_used_hours": float
    }
    """

    def post(self, request):
        req = TripRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = req.validated_data

        try:
            current = geocode(data["current_location"])
            pickup = geocode(data["pickup_location"])
            dropoff = geocode(data["dropoff_location"])
        except GeocodingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            route = get_route([current, pickup, dropoff])
        except RoutingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        engine = HOSEngine(
            ruleset=settings.HOS_RULESET,
            start_time=datetime.now().replace(second=0, microsecond=0),
            cycle_used_hours=data["current_cycle_used_hours"],
        )
        segments = engine.plan(
            total_driving_hours=route["duration_hours"],
            distance_miles=route["distance_miles"],
        )
        days = split_into_days(segments)

        trip = Trip.objects.create(
            current_location=data["current_location"],
            pickup_location=data["pickup_location"],
            dropoff_location=data["dropoff_location"],
            current_cycle_used_hours=data["current_cycle_used_hours"],
            distance_miles=route["distance_miles"],
            duration_hours=route["duration_hours"],
            route_geometry=route["geometry"],
            stops=[
                {"type": "current", **current},
                {"type": "pickup", **pickup},
                {"type": "dropoff", **dropoff},
            ],
        )

        trip.planning_summary = engine.get_summary()

        for day in days:
            LogSheet.objects.create(
                trip=trip,
                day_number=day["day_number"],
                date=day["date"],
                segments=day["segments"],
                total_off_duty_hours=round(day["totals"]["OFF_DUTY"], 2),
                total_sleeper_berth_hours=round(day["totals"]["SLEEPER_BERTH"], 2),
                total_driving_hours=round(day["totals"]["DRIVING"], 2),
                total_on_duty_hours=round(day["totals"]["ON_DUTY"], 2),
            )

        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)


class TripDetailView(APIView):
    """GET /api/trips/<id>/ — retrieve a previously computed trip."""

    def get(self, request, pk):
        try:
            trip = Trip.objects.get(pk=pk)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TripSerializer(trip).data)
