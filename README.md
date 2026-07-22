# RouteLogix

A full-stack trip planner for property-carrying truck drivers. Given a current location, pickup, dropoff, and hours already used in the driver's 70-hour/8-day cycle, it plans the route, simulates FMCSA Hours-of-Service rules over the trip, and generates filled-out, FMCSA-style daily driver's log sheets.

**Live app:** https://route-logix-topaz.vercel.app
**API:** https://routelogix.onrender.com/api/health/
**Repo:** https://github.com/maryaminam/RouteLogix

> Built with Django REST Framework (backend) + React/Vite (frontend).

---

## What it does

1. Takes current location, pickup, dropoff, and current cycle hours used.
2. Geocodes all three locations and computes a driving route (distance,
   duration, turn-by-turn geometry).
3. Simulates the trip forward in time against FMCSA Hours-of-Service rules:
   - 11-hour driving limit
   - 14-hour on-duty window
   - Mandatory 30-minute break after 8 cumulative driving hours
   - 10-hour daily reset (modeled as sleeper berth time)
   - 70-hour/8-day cycle limit, triggering a 34-hour restart when exhausted
     (modeled as off duty)
   - 1 hour on-duty for pickup, 1 hour on-duty for drop-off
   - A fuel stop roughly every 1,000 miles
4. Splits the resulting duty-status timeline into one FMCSA-style daily log
   sheet per calendar day, each totaling a full 24 hours (padded with off-duty
   time before/after actual activity, as real ELD logs do).
5. Reverse-geocodes the location of every duty-status change and attaches it
   as a "Remarks" entry on each log sheet, matching the FMCSA paper log format.
6. Renders the route on an interactive map and each day's log as an SVG grid
   matching the official Driver's Daily Log layout, with a cycle-hours summary
   (used before/after trip, remaining, whether a restart was required) and a
   downloadable PDF per day.

---

## Project structure

```
RouteLogix/
├── backend/                       # Django + DRF API
│   ├── config/                    # settings, urls
│   ├── trips/
│   │   ├── models.py              # Trip, LogSheet
│   │   ├── serializers.py
│   │   ├── views.py                # POST /api/trips/plan/, GET /api/trips/<id>/
│   │   ├── services/
│   │   │   ├── geocoding.py        # Nominatim geocode + reverse_geocode, throttled/retried
│   │   │   ├── routing.py          # OSRM route + polyline interpolation along the route
│   │   │   ├── route_locations.py  # RouteLocator: joins mileage -> coordinates -> place name, per-trip cache
│   │   │   ├── hos_engine.py       # core HOS simulation (pure Python, unit-tested)
│   │   │   └── daily_split.py      # splits the timeline into 24h log-sheet days + remarks
│   │   └── tests/
│   │       └── test_hos_engine.py
│   ├── requirements.txt
│   ├── Procfile
│   └── .env.example
└── frontend/                       # React (Vite) SPA
    ├── src/
    │   ├── components/
    │   │   ├── TripForm.jsx
    │   │   ├── RouteMap.jsx        # Leaflet + OpenStreetMap tiles
    │   │   └── ELDLogSheet.jsx     # SVG FMCSA-style daily log grid, remarks, PDF export
    │   ├── pages/Home.jsx
    │   └── api.js
    ├── vercel.json
    └── .env.example
```

---

## Running locally

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python3 manage.py migrate
python3 manage.py runserver
```
API at `http://127.0.0.1:8000/api/`. Health check: `GET /api/health/`.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
App at `http://localhost:5173`.

### Backend tests
```bash
cd backend
python3 manage.py test trips
```
`trips/services/hos_engine.py` is the core logic and has dedicated unit tests
covering the 11-hour driving limit, 14-hour window, 30-minute break rule,
sleeper-berth vs. off-duty reset behavior, 70-hour/8-day cycle limit + 34-hour
restart, and that every generated log sheet totals 24 hours.

---

## Assumptions

- Property-carrying driver, using the 70-hour/8-day cycle (not 60/7).
- No adverse driving conditions exception applied.
- Fueling at least once every 1,000 miles.
- 1 hour each for pickup and drop-off.
- Average driving speed for HOS timing is derived from the actual route
  (`distance / duration` from the routing provider), not a fixed assumption,
  so fuel-stop spacing and pickup/drop-off timing reflect the real route.

---

## Known limitations

- **70-hour/8-day cycle is a single accumulating total, not a true rolling
  8-day window.** The app takes one aggregate "current cycle used" number as
  input rather than a day-by-day duty history, so a true rolling window isn't
  reconstructable from the given input. This is intentional and conservative:
  it can only ever call for rest earlier or more than a true rolling window
  would, never less, so it never produces an HOS violation — only a
  possibly-premature rest recommendation on trips spanning more than 8 days.
- **Geocoding rate limits.** The public Nominatim (OpenStreetMap) server caps
  requests at roughly 1/second and can block traffic without a legitimate
  User-Agent. The app throttles and retries around this, but trip-planning
  latency scales with the number of distinct duty-status locations (~1.1s per
  unique location, cached per-trip). A multi-day trip with many stops can add
  10-15+ seconds to `POST /api/trips/plan/`. If this becomes a problem, set
  `GEOCODING_API_KEY` and `NOMINATIM_BASE_URL` to a key-based provider like
  LocationIQ (free tier, 5,000 req/day) — no code changes required.
- **Render free-tier cold starts.** The backend spins down after 15 minutes
  of inactivity; the first request after idle can take 30-60 seconds to
  respond while the instance wakes up.
- **Render's free tier does not run Procfile `release:` phases** (that's a
  Heroku-specific convention Render doesn't implement). Migrations run as
  part of the web service's start command instead
  (`python manage.py migrate && gunicorn config.wsgi`), which re-runs safely
  on every boot since Django migrations are idempotent.

---

## Deployment

- **Backend** → Render (free web service tier, no credit card required for
  the free instance type). Database is **Neon Postgres** (free, no card, no
  expiry) rather than Render's built-in Postgres, since Render's free
  Postgres is hard-deleted 30 days after creation.
- **Frontend** → Vercel (free Hobby tier).

Root Directory must be set to `frontend` on Vercel and `backend` on Render —
this is a monorepo with both apps in one GitHub repository.
