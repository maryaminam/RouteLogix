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

Typeahead suggestions (search_locations) are the exception: Nominatim matches
whole words only, so "denv" finds nothing useful. Those go to Photon, the OSM
project's autocomplete engine, which does prefix matching and is not subject to
the throttle below. Nominatim remains the authority for resolving a location
once chosen, and backs Photon up if it's unreachable.
"""

import logging
import time
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

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


def _request(path: str, params: dict, what: str, _retries: int = 2):
    """
    Performs a throttled, retrying GET against the configured Nominatim-compatible
    provider and returns the decoded JSON body.

    `what` is a human description of the lookup, used in error messages.
    """
    url = f"{settings.NOMINATIM_BASE_URL}/{path}"
    params = {**params, "format": "json"}
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
                    f"{what}. If this persists, the public Nominatim "
                    f"server is likely blocking this traffic — set GEOCODING_API_KEY "
                    f"and NOMINATIM_BASE_URL to a provider like LocationIQ in your .env."
                )
                time.sleep(1.5 * (attempt + 1))
                continue

            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = GeocodingError(f"Geocoding request failed for {what}: {exc}")

    raise last_error


def geocode(location_text: str) -> dict:
    """
    Returns {"lat": float, "lng": float, "display_name": str}
    Raises GeocodingError if the location can't be resolved.
    """
    results = _request(
        "search",
        {"q": location_text, "limit": 1},
        what=repr(location_text),
    )

    if not results:
        raise GeocodingError(f"Could not geocode location: {location_text!r}")

    top = results[0]
    return {
        "lat": float(top["lat"]),
        "lng": float(top["lon"]),
        "display_name": top.get("display_name", location_text),
    }


# Nominatim's address payload names the populated place differently depending on
# how the area is tagged in OSM, so fall back through the plausible keys.
_CITY_KEYS = ("city", "town", "village", "hamlet", "municipality", "suburb", "county")


def _format_city_state(address: dict) -> str:
    """Condenses a Nominatim address dict into the "City, ST" form used on log sheets."""
    city = next((address[key] for key in _CITY_KEYS if address.get(key)), None)

    # ISO3166-2-lvl4 looks like "US-CA"; its suffix is the two-letter state code
    # drivers actually write in the remarks row.
    iso = address.get("ISO3166-2-lvl4") or ""
    state = iso.split("-")[-1] if "-" in iso else address.get("state")

    return ", ".join(part for part in (city, state) if part)


_US_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "puerto rico": "PR",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def _allowed_country_codes() -> set:
    return {
        code.strip().upper()
        for code in (settings.LOCATION_SEARCH_COUNTRY_CODES or "").split(",")
        if code.strip()
    }


def _suggestion(value, label, context, lat, lng) -> dict:
    return {"value": value, "label": label, "context": context, "lat": lat, "lng": lng}


def _dedupe(suggestions: list[dict]) -> list[dict]:
    """
    Both providers return several records that collapse to the same city — a
    boundary, a place node, a suburb. Show each place once, keeping the first
    (best-ranked) of each.
    """
    seen = set()
    unique = []
    for suggestion in suggestions:
        key = suggestion["value"].casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(suggestion)
    return unique


def _search_photon(query: str, limit: int) -> list[dict]:
    """
    Typeahead suggestions from Photon, which does prefix matching ("denv" ->
    Denver) where Nominatim only matches whole words.

    Photon has no country filter, so we over-fetch and filter here.
    """
    countries = _allowed_country_codes()
    try:
        response = requests.get(
            f"{settings.PHOTON_BASE_URL}/api",
            params={"q": query, "limit": limit * 3 if countries else limit,
                    "lang": "en", "layer": "city"},
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT, "Accept": "application/json"},
            timeout=6,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Photon suggestion lookup failed for {query!r}: {exc}")

    suggestions = []
    for feature in features:
        properties = feature.get("properties") or {}
        if countries and (properties.get("countrycode") or "").upper() not in countries:
            continue

        name = properties.get("name")
        if not name:
            continue

        # Photon gives the full state name; the log sheets and the rest of the
        # UI speak in two-letter codes.
        state = properties.get("state") or ""
        state_code = _US_STATE_CODES.get(state.casefold(), state)

        coordinates = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        if coordinates[0] is None:
            continue

        context = ", ".join(
            part for part in (properties.get("county"), state, properties.get("country")) if part
        )
        suggestions.append(_suggestion(
            value=", ".join(part for part in (name, state_code) if part),
            label=name,
            context=context,
            lat=float(coordinates[1]),
            lng=float(coordinates[0]),
        ))

    return _dedupe(suggestions)[:limit]


def _search_nominatim(query: str, limit: int) -> list[dict]:
    """
    Fallback suggestions from Nominatim. Only matches complete words, so
    partial input tends to return little — acceptable for a fallback.
    """
    params = {"q": query, "limit": limit, "addressdetails": 1}
    country_codes = settings.LOCATION_SEARCH_COUNTRY_CODES
    if country_codes:
        params["countrycodes"] = country_codes

    results = _request("search", params, what=f"suggestions for {query!r}")

    suggestions = []
    for item in results or []:
        address = item.get("address") or {}
        display_name = item.get("display_name", "")
        value = _format_city_state(address) or display_name
        if not value:
            continue

        # Drop the leading name from the context line so the dropdown doesn't
        # read "Omaha — Omaha, Douglas County, ...".
        context = display_name.split(", ", 1)[-1] if ", " in display_name else ""
        suggestions.append(_suggestion(
            value=value,
            label=next((key_ for key_ in (address.get(k) for k in _CITY_KEYS) if key_), value),
            context=context,
            lat=float(item["lat"]),
            lng=float(item["lon"]),
        ))

    return _dedupe(suggestions)


def search_locations(query: str, limit: int = None) -> list[dict]:
    """
    Returns up to `limit` place suggestions for a partial query, for the
    location autocomplete:

        [{"value": "Omaha, NE",        # what goes into the input, and what
                                       #   geocode() will later resolve
          "label": "Omaha",            # primary line in the dropdown
          "context": "Douglas County, Nebraska, United States",
          "lat": float, "lng": float}, ...]

    Raises GeocodingError only if every provider fails.

    Suggestions are emitted as "City, ST" rather than a provider's full display
    name, so that picking one hands the planner a string it is known to be able
    to geocode, and so log remarks come out in the same form.
    """
    limit = limit or settings.LOCATION_SEARCH_LIMIT

    if settings.PHOTON_BASE_URL:
        try:
            return _search_photon(query, limit)
        except GeocodingError as exc:
            logger.warning("Falling back to Nominatim for suggestions: %s", exc)

    return _search_nominatim(query, limit)


def reverse_geocode(lat: float, lng: float) -> dict:
    """
    Resolves a coordinate to the nearest populated place.

    Returns {"lat", "lng", "city_state": "City, ST", "display_name": str}.
    Raises GeocodingError if the coordinate can't be resolved.

    zoom=10 asks Nominatim for city-level granularity — street-level detail is
    meaningless here since the coordinate is itself an interpolated estimate.
    """
    result = _request(
        "reverse",
        {"lat": lat, "lon": lng, "zoom": 10, "addressdetails": 1},
        what=f"coordinate ({lat}, {lng})",
    )

    if not result or result.get("error"):
        raise GeocodingError(f"Could not reverse geocode coordinate ({lat}, {lng})")

    display_name = result.get("display_name", "")
    return {
        "lat": lat,
        "lng": lng,
        "city_state": _format_city_state(result.get("address") or {}) or display_name,
        "display_name": display_name,
    }
