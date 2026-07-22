"""
Django settings for the ELD Trip Planner project.
"""

from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv())

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "corsheaders",
    # local
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# I18N
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# CORS — allow the deployed React frontend + local dev server
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://127.0.0.1:5173",
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

# ---------------------------------------------------------------------------
# App-specific settings (routing/geocoding provider, HOS constants)
# ---------------------------------------------------------------------------
OSRM_BASE_URL = config("OSRM_BASE_URL", default="https://router.project-osrm.org")
NOMINATIM_BASE_URL = config("NOMINATIM_BASE_URL", default="https://nominatim.openstreetmap.org")
NOMINATIM_USER_AGENT = config("NOMINATIM_USER_AGENT", default="ELDTripPlannerApp/1.0")
# Optional: set this to switch to a key-based geocoding provider (e.g. LocationIQ)
# if the public Nominatim server blocks your traffic. Leave blank to use plain
# Nominatim with no key.
GEOCODING_API_KEY = config("GEOCODING_API_KEY", default="")

# Location autocomplete. Nominatim matches whole words only ("denv" finds
# nothing useful), so suggestions come from Photon, the OSM project's
# purpose-built typeahead engine. Nominatim stays the authority for actually
# resolving a chosen location, and is the fallback if Photon is unreachable.
# Set to blank to skip Photon entirely and use Nominatim for suggestions too.
PHOTON_BASE_URL = config("PHOTON_BASE_URL", default="https://photon.komoot.io")
# Results are cached hard regardless of provider: place names don't move, and
# both services are free instances we shouldn't hammer on every keystroke.
LOCATION_SEARCH_MIN_QUERY_LENGTH = config("LOCATION_SEARCH_MIN_QUERY_LENGTH", default=3, cast=int)
LOCATION_SEARCH_LIMIT = config("LOCATION_SEARCH_LIMIT", default=6, cast=int)
LOCATION_SEARCH_CACHE_SECONDS = config("LOCATION_SEARCH_CACHE_SECONDS", default=60 * 60 * 24, cast=int)
# Restricts suggestions to one or more ISO country codes. Defaults to US since
# the HOS ruleset and "City, ST" log remarks are FMCSA-specific; blank to allow
# anywhere (useful for cross-border runs).
LOCATION_SEARCH_COUNTRY_CODES = config("LOCATION_SEARCH_COUNTRY_CODES", default="us")

# Log-sheet remarks reverse-geocode every duty-status change, and the throttle
# above makes each miss cost about a second of request time. Towns don't move,
# and trips down the same interstate stop in the same places, so these are held
# far longer than they are likely to change.
REVERSE_GEOCODE_CACHE_SECONDS = config(
    "REVERSE_GEOCODE_CACHE_SECONDS", default=60 * 60 * 24 * 30, cast=int
)

HOS_RULESET = {
    "MAX_DRIVING_HOURS": 11,
    "MAX_DUTY_WINDOW_HOURS": 14,
    "REQUIRED_OFF_DUTY_HOURS": 10,
    "RESET_STATUS": "SLEEPER_BERTH",
    "DRIVING_BREAK_TRIGGER_HOURS": 8,
    "REQUIRED_BREAK_MINUTES": 30,
    "MAX_CYCLE_HOURS": 70,
    "CYCLE_WINDOW_DAYS": 8,
    "RESTART_HOURS": 34,
    "PICKUP_DURATION_HOURS": 1,
    "DROPOFF_DURATION_HOURS": 1,
    "FUEL_INTERVAL_MILES": 1000,
    "FUEL_STOP_DURATION_HOURS": 0.5,
    "AVERAGE_DRIVING_SPEED_MPH": 55,
}
