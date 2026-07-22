import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import TripRequestSerializer, TripSerializer
from .models import Trip, LogSheet
from .services.geocoding import geocode, search_locations, GeocodingError
from .services.routing import get_route, RoutingError
from .services.hos_engine import HOSEngine
from .services.daily_split import split_into_days
from .services.route_locations import RouteLocator


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

        # § 395.8(d): a log's 24-hour period runs on home terminal time, whatever
        # zones the driver crosses. Planning from the server's clock instead put
        # the day boundary at UTC midnight, so a driver starting at 6pm Pacific
        # saw their log day roll over at 4pm local. The zone is validated by the
        # serializer, so ZoneInfo() cannot raise here.
        home_terminal = ZoneInfo(data["home_terminal_timezone"])
        engine = HOSEngine(
            ruleset=settings.HOS_RULESET,
            start_time=datetime.now(home_terminal).replace(second=0, microsecond=0),
            cycle_used_hours=data["current_cycle_used_hours"],
        )
        segments = engine.plan(route["legs"])
        # Reverse-geocodes each duty-status change to a city/state for the log
        # sheet remarks. Scoped to this request so its cache lives and dies with
        # the trip it was built for.
        locator = RouteLocator(route["legs"])
        days = split_into_days(segments, locate=locator.locate)

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


class LocationSearchView(APIView):
    """
    GET /api/locations/search/?q=<partial>

    Typeahead suggestions for the trip form's location fields.

    Every miss costs a call to Nominatim, which throttles this process to about
    one request per second and blocks bursty traffic outright. So results are
    cached aggressively — place names are stable, and a user typing "omaha"
    walks through prefixes that other users will type too.
    """

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()

        if len(query) < settings.LOCATION_SEARCH_MIN_QUERY_LENGTH:
            return Response({"results": [], "query": query})

        # Hash rather than interpolate: the raw query is user input and would
        # otherwise land in cache keys containing spaces and control characters.
        digest = hashlib.sha256(query.casefold().encode("utf-8")).hexdigest()[:32]
        cache_key = f"location-search:{digest}"

        cached = cache.get(cache_key)
        if cached is not None:
            return Response({"results": cached, "query": query, "cached": True})

        try:
            results = search_locations(query)
        except GeocodingError as exc:
            # The field still accepts free text, so this degrades rather than
            # blocks — say so plainly instead of returning an empty list, which
            # the UI would otherwise render as "no matches".
            return Response(
                {"detail": str(exc), "results": []},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cache.set(cache_key, results, settings.LOCATION_SEARCH_CACHE_SECONDS)
        return Response({"results": results, "query": query, "cached": False})


class TripDetailView(APIView):
    """GET /api/trips/<id>/ — retrieve a previously computed trip."""

    def get(self, request, pk):
        try:
            trip = Trip.objects.get(pk=pk)
        except Trip.DoesNotExist:
            return Response({"detail": "Trip not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TripSerializer(trip).data)
