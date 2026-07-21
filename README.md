# ELD Trip Planner

Full-stack app that takes trip details (current location, pickup, dropoff,
current 70hr/8day cycle hours used) and outputs:

1. A map of the route with stops (pickup, dropoff, fuel, rests).
2. FMCSA-style daily log sheets (Driver's Daily Log grid), auto-filled,
   split across multiple days for longer trips.

Built with **Django REST Framework** (backend) + **React/Vite** (frontend).

## Project structure

```
eld-trip-planner/
├── backend/                  # Django + DRF API
│   ├── config/                # project settings, urls
│   ├── trips/                 # the one app: models, views, serializers
│   │   ├── services/
│   │   │   ├── geocoding.py   # Nominatim (OpenStreetMap) geocoding
│   │   │   ├── routing.py     # OSRM route/distance/duration
│   │   │   ├── hos_engine.py  # core HOS simulation (pure Python, unit-tested)
│   │   │   └── daily_split.py # splits the timeline into 24h log sheets
│   │   └── tests/
│   ├── requirements.txt
│   ├── Procfile               # for Render/Railway/Heroku-style deploy
│   └── .env.example
└── frontend/                  # React (Vite) SPA
    ├── src/
    │   ├── components/        # TripForm, RouteMap, DailyLogSheet
    │   ├── pages/Home.jsx
    │   └── api.js              # fetch wrapper to the Django API
    ├── vercel.json
    └── .env.example
```

## Running locally

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 manage.py migrate
python3 manage.py runserver
```
API available at `http://127.0.0.1:8000/api/`. Health check: `GET /api/health/`.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
App available at `http://localhost:5173`.

## Running backend tests
```bash
cd backend
python3 manage.py test trips
```
The HOS engine (`trips/services/hos_engine.py`) is the core logic and has
dedicated unit tests in `trips/tests/test_hos_engine.py` covering the
11-hour driving limit, 14-hour window, 30-minute break rule, 70-hour/8-day
cycle limit + 34-hour restart, and that daily log sheets total 24 hours.

## Assumptions (per assessment brief)
- Property-carrying driver, 70hrs/8days cycle, no adverse driving conditions.
- Fueling at least once every 1,000 miles.
- 1 hour each for pickup and drop-off.

## Deployment
- **Backend** → Render/Railway (free tier). Uses `gunicorn` + `whitenoise`
  for static files, `Procfile` included. Set env vars from `.env.example`,
  plus `CORS_ALLOWED_ORIGINS` to your deployed frontend URL.
- **Frontend** → Vercel. Set `VITE_API_URL` to your deployed backend URL.

## Status
- [x] Project scaffolding (this step)
- [x] HOS simulation engine + unit tests
- [ ] Real map rendering polish (markers, stop icons, popups)
- [ ] FMCSA-accurate SVG daily log grid (currently a JSON placeholder)
- [ ] End-to-end test against live OSRM/Nominatim
- [ ] Deployment
