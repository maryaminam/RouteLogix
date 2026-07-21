"""
Geocoding service — resolves free-text location strings to (lat, lng).

Default provider is OpenStreetMap's Nominatim public demo server, which is
free and requires no signup, but enforces a strict usage policy:
  - You MUST send a real, descriptive User-Agent (not a placeholder/example).
  - You MUST NOT send more than ~1 request/second.
Violating either gets requests silently blocked with a 403.

If you hit persistent 403s (common on the shared public instance), set
GEOCODING_API_KEY in your .env to switch to a free-tier key-based provider
like LocationIQ (https://locationiq.com — 5,000 free requests/day) without
changing any code — see NOMINATIM_BASE_URL in .env.example.
"""

import time
import requests
from django.conf import settings

# Track the last request time at module level so every call across the
# process respects Nominatim's ~1 req/sec limit, even across multiple
# geocode() calls made back-to-back for the same trip.
_last_request_at = 0.0
_MIN_INTERVAL_SECONDS = 1.1


class GeocodingError(Exception):
    pass


def _throttle():
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def geocode(location_text: str, _retries: int = 2) -> dict:
    """
    Returns {"lat": float, "lng": float, "display_name": str}
    Raises GeocodingError if the location can't be resolved.
    """
    url = f"{settings.NOMINATIM_BASE_URL}/search"
    params = {"q": location_text, "format": "json", "limit": 1}
    if settings.GEOCODING_API_KEY:
        params["key"] = settings.GEOCODING_API_KEY

    headers = {
        "User-Agent": settings.NOMINATIM_USER_AGENT,
        "Accept": "application/json",
    }

    last_error = None
    for attempt in range(_retries + 1):
        _throttle()
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code in (403, 429):
                # Likely rate-limited or blocked — back off and retry once or twice.
                last_error = GeocodingError(
                    f"Geocoding provider returned {response.status_code} for "
                    f"{location_text!r}. If this persists, the public Nominatim "
                    f"server is likely blocking this traffic — set GEOCODING_API_KEY "
                    f"and NOMINATIM_BASE_URL to a provider like LocationIQ in your .env."
                )
                time.sleep(1.5 * (attempt + 1))
                continue

            response.raise_for_status()
            results = response.json()

            if not results:
                raise GeocodingError(f"Could not geocode location: {location_text!r}")

            top = results[0]
            return {
                "lat": float(top["lat"]),
                "lng": float(top["lon"]),
                "display_name": top.get("display_name", location_text),
            }
        except requests.RequestException as exc:
            last_error = GeocodingError(f"Geocoding request failed for {location_text!r}: {exc}")

    raise last_error
