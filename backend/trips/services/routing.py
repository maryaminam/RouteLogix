"""
Routing service — computes a driving route between an ordered list of
waypoints using the public OSRM demo server (free, no API key required).
"""

import math

import requests
from django.conf import settings

EARTH_RADIUS_MILES = 3958.8


class RoutingError(Exception):
    pass


def get_route(waypoints: list[dict]) -> dict:
    """
    waypoints: list of {"lat": float, "lng": float}, in visiting order.

    Returns:
        {
            "distance_miles": float,
            "duration_hours": float,
            "geometry": [[lat, lng], ...],   # decoded route line for the map
            "legs": [{"distance_miles": float, "duration_hours": float,
                      "geometry": [[lat, lng], ...]}, ...]
        }

    Each leg carries its own slice of the route line, so callers can locate a
    point *within* a leg without the leg boundaries drifting off the waypoints.
    """
    coords = ";".join(f"{wp['lng']},{wp['lat']}" for wp in waypoints)
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM could not compute a route: {data.get('message', data)}")

    route = data["routes"][0]
    meters_to_miles = 0.000621371
    seconds_to_hours = 1 / 3600

    geometry = [[lat, lng] for lng, lat in route["geometry"]["coordinates"]]

    # OSRM echoes back each input waypoint snapped to the road network; those
    # snapped points are where the route line is actually cut into legs.
    snapped = [
        [waypoint["location"][1], waypoint["location"][0]]
        for waypoint in data.get("waypoints", [])
    ] or [[wp["lat"], wp["lng"]] for wp in waypoints]
    leg_geometries = split_geometry_by_waypoints(geometry, snapped)

    legs = [
        {
            "distance_miles": leg["distance"] * meters_to_miles,
            "duration_hours": leg["duration"] * seconds_to_hours,
            "geometry": leg_geometry,
        }
        for leg, leg_geometry in zip(route["legs"], leg_geometries)
    ]

    return {
        "distance_miles": route["distance"] * meters_to_miles,
        "duration_hours": route["duration"] * seconds_to_hours,
        "geometry": geometry,
        "legs": legs,
    }


def _haversine_miles(a: list, b: list) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def _nearest_vertex_index(geometry: list, point: list, start: int = 0) -> int:
    """Index of the vertex at or after `start` lying closest to `point`."""
    best_index = start
    best_distance = float("inf")
    for index in range(start, len(geometry)):
        distance = _haversine_miles(geometry[index], point)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def split_geometry_by_waypoints(geometry: list, waypoints: list) -> list[list]:
    """
    Cuts the full route line into one sub-line per leg, splitting at the vertex
    nearest each intermediate waypoint.

    Consecutive legs share the vertex they meet at, so the end of one leg and
    the start of the next both resolve to the waypoint between them — which is
    what lets a pickup be located at the pickup rather than somewhere near it.

    Always returns exactly len(waypoints) - 1 sub-lines, so callers can zip it
    against the leg list without silently losing a leg.
    """
    if len(waypoints) < 2:
        return [geometry]

    # A route too short to cut gives every leg the same degenerate line; the
    # leg count still has to match.
    if len(geometry) < 2:
        return [geometry] * (len(waypoints) - 1)

    # Search forward from the previous boundary so the cuts stay in route order
    # even when the line doubles back near a waypoint.
    boundaries = [0]
    for waypoint in waypoints[1:-1]:
        boundaries.append(_nearest_vertex_index(geometry, waypoint, start=boundaries[-1]))
    boundaries.append(len(geometry) - 1)

    return [
        geometry[start:end + 1]
        for start, end in zip(boundaries, boundaries[1:])
    ]


def cumulative_distances(geometry: list) -> list[float]:
    """
    Running along-route distance in miles at each vertex of `geometry`
    (a list of [lat, lng]). The first entry is always 0.
    """
    totals = [0.0]
    for previous, current in zip(geometry, geometry[1:]):
        totals.append(totals[-1] + _haversine_miles(previous, current))
    return totals


def point_at_fraction(geometry: list, fraction: float, totals: list[float] = None) -> list:
    """
    Returns the [lat, lng] lying `fraction` (0..1) of the way along the route by
    distance, linearly interpolating within whichever polyline leg it falls on.

    Pass `totals` from cumulative_distances() to avoid recomputing it when
    resolving many points on the same route.
    """
    if not geometry:
        raise RoutingError("Cannot locate a point on an empty route geometry.")
    if len(geometry) == 1:
        return list(geometry[0])

    if totals is None:
        totals = cumulative_distances(geometry)

    route_length = totals[-1]
    fraction = min(max(fraction, 0.0), 1.0)
    if route_length <= 0:
        return list(geometry[0])

    target = fraction * route_length

    # Walk to the first vertex at or past the target, then interpolate backwards
    # into the leg that contains it.
    for index in range(1, len(totals)):
        if totals[index] >= target:
            leg_length = totals[index] - totals[index - 1]
            ratio = (target - totals[index - 1]) / leg_length if leg_length > 0 else 0.0
            start = geometry[index - 1]
            end = geometry[index]
            return [
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            ]

    return list(geometry[-1])
