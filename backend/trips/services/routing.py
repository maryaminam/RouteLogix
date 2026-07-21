"""
Routing service — computes a driving route between an ordered list of
waypoints using the public OSRM demo server (free, no API key required).
"""

import requests
from django.conf import settings


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
            "legs": [{"distance_miles": float, "duration_hours": float}, ...]
        }
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

    legs = [
        {
            "distance_miles": leg["distance"] * meters_to_miles,
            "duration_hours": leg["duration"] * seconds_to_hours,
        }
        for leg in route["legs"]
    ]

    return {
        "distance_miles": route["distance"] * meters_to_miles,
        "duration_hours": route["duration"] * seconds_to_hours,
        "geometry": geometry,
        "legs": legs,
    }
