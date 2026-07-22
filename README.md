# RouteLogix

A real-world commercial driver cannot simply drive non-stop from point A to point B. This application serves as an automated dispatcher and safety compliance officer by taking simple trip inputs; Current Location, Pickup Location, Dropoff Location, and Current Cycle Used (Hours) and producing two critical outputs:  
1. An Interactive Route Map: Visually displaying the full path along with specific waypoints for pickup, dropoff, mandatory 30-minute rest breaks, 10-hour overnight sleeps, and fueling stops.  
2. Automated Daily Log Sheets: Generating accurate 24-hour FMCSA graph grids (Off Duty, Sleeper Berth, Driving, On Duty Not Driving) for every day of the trip, complete with duty-status change remarks and daily hour recaps. 

Built with **Django REST Framework** (backend) + **React/Vite** (frontend).

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
- Trip start time is localized to the browser's detected timezone, treated as a
  proxy for the driver's home terminal timezone, per FMCSA guidance that all log
  times use home terminal time.

## Deployment
- **Backend** → Render (free tier). Uses `gunicorn` + `whitenoise`
  for static files, `Procfile` included.
- **Frontend** → Vercel. Set `VITE_API_URL` to your deployed backend URL.

### Database

Locally there is nothing to configure: with no `DATABASE_URL` set, the app uses
the sqlite file at `backend/db.sqlite3`. In production it reads `DATABASE_URL`
and switches to Postgres.

Render's filesystem is ephemeral, so sqlite there is not merely slow but
lossy — the file is recreated empty on every deploy and every restart, taking
all saved trips with it. Provision a real database:

1. In the Render dashboard choose **New → PostgreSQL**. The free instance is
   enough for this app.
2. Open the new database and copy the **Internal Database URL**, not the
   external one. The internal URL keeps traffic on Render's private network,
   which is faster and needs no SSL configuration. (The external URL is for
   connecting from your own machine, and expects `?sslmode=require`.)
3. In the **web service's** environment (not the database's), add
   `DATABASE_URL` with that value.
4. Migrations run automatically — the `release:` line in `backend/Procfile`
   already runs `migrate`, and Render executes it on every deploy before the new
   version starts serving. Redeploy after setting the variable so it runs
   against Postgres. To apply them by hand instead, use the web service's
   **Shell** tab:

   ```bash
   python manage.py migrate
   ```

The free Postgres tier idles out inactive connections, so the app reuses
connections for ten minutes (`conn_max_age`) with health checks enabled — see
the comment in `config/settings.py` for why the two belong together.

With `DEBUG=False` the app also turns on HTTPS redirects, `Secure` session and
CSRF cookies, and one year of HSTS with `includeSubDomains` and `preload`.
`python manage.py check --deploy` reports no issues in that configuration.
