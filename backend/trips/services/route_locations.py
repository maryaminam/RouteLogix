"""
Estimates *where* a driver was when a duty status changed, so the daily log
sheets can carry the "Remarks" entries the FMCSA form requires (a city/state
for every change of duty status).

We have no continuous GPS feed — only the planned route geometry and how far
the HOS engine says the driver had travelled at that moment. So we interpolate
along the route line by distance and reverse-geocode the resulting point.

Interpolation is done per leg rather than over the whole trip. Road distance
and straight-line polyline distance disagree by a few percent, so a single
trip-wide fraction would drift; anchoring each leg to its own sub-line keeps
the leg boundaries exactly on the pickup and drop-off waypoints, which are the
two locations a log auditor actually cares about.

Reverse geocoding is rate-limited to roughly one call per second (see
geocoding.py), so a locator instance caches results for the trip it was built
for. Coordinates are rounded to ~1 km before being used as the cache key, which
collapses the many status changes that happen at the same place — the start and
end of a rest period, a fuel stop, a 30-minute break — into a single lookup.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from .geocoding import reverse_geocode, GeocodingError
from .routing import cumulative_distances, point_at_fraction

logger = logging.getLogger(__name__)

# ~2 decimal places of latitude/longitude, i.e. a bit over a kilometre. Any two
# status changes closer together than this get the same remark anyway.
_CACHE_PRECISION = 2


class RouteLocator:
    """Resolves a position on a route leg to a "City, ST" remark, caching per trip."""

    def __init__(self, legs: list[dict]):
        """
        legs: the list from routing.get_route(), each entry carrying its own
        "geometry" sub-line and "distance_miles".
        """
        self.legs = legs or []
        self._geometries = [leg.get("geometry") or [] for leg in self.legs]
        self._totals = [
            cumulative_distances(geometry) if geometry else []
            for geometry in self._geometries
        ]
        self._cache: dict[tuple, str] = {}

    def position(self, leg_index: int, miles_into_leg: float) -> list | None:
        """
        Returns [lat, lng] for a point `miles_into_leg` along leg `leg_index`,
        or None if that leg has no usable geometry.
        """
        if not (0 <= leg_index < len(self._geometries)):
            return None

        geometry = self._geometries[leg_index]
        if not geometry:
            return None

        leg_miles = self.legs[leg_index].get("distance_miles") or 0.0
        # A leg with no length is a degenerate waypoint pair; its start is the
        # only point it has.
        fraction = miles_into_leg / leg_miles if leg_miles > 0 else 0.0
        return point_at_fraction(geometry, fraction, self._totals[leg_index])

    def locate(self, leg_index: int, miles_into_leg: float) -> str:
        """
        Returns "City, ST" for that position, or "" if it can't be resolved.

        Never raises: a missing remark degrades the log sheet, it shouldn't fail
        the whole trip-planning request.
        """
        point = self.position(leg_index, miles_into_leg)
        if point is None:
            return ""

        lat, lng = point
        key = (round(lat, _CACHE_PRECISION), round(lng, _CACHE_PRECISION))
        if key in self._cache:
            return self._cache[key]

        # Then the shared cache, which outlives this request. Every trip down a
        # given interstate stops in the same handful of towns, so this is what
        # keeps a long trip from spending its whole request budget in the 1.1s
        # throttle. Rounded coordinates make the key naturally shareable.
        shared_key = f"reverse-geocode:{key[0]}:{key[1]}"
        remark = cache.get(shared_key)

        if remark is None:
            try:
                remark = reverse_geocode(lat, lng)["city_state"]
            except GeocodingError as exc:
                logger.warning("Could not reverse geocode (%s, %s): %s", lat, lng, exc)
                # Don't cache a failure — it's usually a transient rate limit,
                # and caching it would blank this town's remark for a whole day.
                self._cache[key] = ""
                return ""
            cache.set(shared_key, remark, settings.REVERSE_GEOCODE_CACHE_SECONDS)

        self._cache[key] = remark
        return remark
