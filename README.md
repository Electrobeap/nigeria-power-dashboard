# Nigeria Power Data

<<<<<<< HEAD
Production-grade Flask energy intelligence dashboard for Nigeria power-grid analytics at `https://nigeriapowerdata.com`.

## Capabilities

- Real-time NISO/NIGGRID data scraping.
- PostgreSQL persistence through SQLAlchemy.
- Flask-Migrate/Alembic migrations.
- APScheduler data collection every 30 minutes.
- Historical generation, DisCo allocation, GenCo performance, and analytics snapshot storage.
- 24-hour and 7-day trends, moving averages, peak generation, outage detection, volatility, and rolling health score.
- Modern responsive dashboard with dark mode, sticky header, status badges, KPI cards, loading states, and polished Chart.js visuals.
- SEO basics: meta tags, OpenGraph tags, favicon, `robots.txt`, and `sitemap.xml`.
- Future AdSense-safe layout zones: sidebar, in-content, and footer slots.

## Project Structure

```text
.
├── app.py
├── grid_monitor/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models.py
│   ├── routes/
│   │   ├── api.py
│   │   └── web.py
│   ├── services/
│   │   ├── analytics.py
│   │   ├── cache.py
│   │   ├── scheduler.py
│   │   ├── scraper.py
│   │   ├── storage.py
│   │   └── validation.py
│   ├── static/
│   │   ├── css/dashboard.css
│   │   ├── js/dashboard.js
│   │   └── favicon.svg
│   ├── templates/index.html
│   └── utils/
│       ├── logging.py
│       └── time.py
├── migrations/
├── Procfile
├── render.yaml
├── requirements.txt
└── runtime.txt
=======
Production-grade Flask energy intelligence dashboard for Nigeria's power grid at
`https://nigeriapowerdata.com`.

The platform collects public NISO/NIGGRID readings, stores historical grid
records in PostgreSQL, and turns generation, GenCo, DisCo, and distribution
signals into operational analytics.

## Core Features

- Real-time NISO/NIGGRID data scraping with retry, timeout, and stale fallback handling.
- PostgreSQL persistence through SQLAlchemy, with SQLite fallback for local development.
- Flask-Migrate/Alembic migration support.
- Automatic startup migrations for Render free-tier deployments without shell access.
- APScheduler data collection every 30 minutes with a single protected job id.
- Historical generation, DisCo allocation, GenCo performance, analytics snapshots, and distribution intelligence snapshots.
- 24-hour and 7-day generation trends, moving averages, peak tracking, outage signals, volatility, and rolling health score.
- Distribution Intelligence module for transformer utilization, overload warnings, settlement growth pressure, and simulated loading trends.
- Modern responsive dashboard with dark mode, KPI cards, loading states, sticky navigation, polished charts, tables, and footer.
- SEO and AdSense readiness: meta tags, OpenGraph/Twitter tags, favicon, logo, semantic HTML, `robots.txt`, `sitemap.xml`, and non-intrusive ad placeholders.

## Project Structure

```text
.
|-- app.py
|-- grid_monitor/
|   |-- __init__.py
|   |-- config.py
|   |-- extensions.py
|   |-- models.py
|   |-- routes/
|   |   |-- api.py
|   |   `-- web.py
|   |-- services/
|   |   |-- analytics.py
|   |   |-- cache.py
|   |   |-- distribution.py
|   |   |-- scheduler.py
|   |   |-- scraper.py
|   |   |-- storage.py
|   |   `-- validation.py
|   |-- static/
|   |   |-- css/dashboard.css
|   |   |-- js/dashboard.js
|   |   |-- favicon.svg
|   |   `-- logo.svg
|   |-- templates/index.html
|   `-- utils/
|       |-- logging.py
|       `-- time.py
|-- migrations/
|   `-- versions/
|-- Procfile
|-- render.yaml
|-- requirements.txt
`-- runtime.txt
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
```

## Architecture

<<<<<<< HEAD
The app uses a Flask application factory in `grid_monitor/__init__.py`.

- `models.py` defines `grid_snapshots`, `genco_data`, `disco_data`, and `analytics_snapshots`.
- `services/scraper.py` handles NISO/NIGGRID fetches, parsing, retries, timeouts, and stale cache fallback.
- `services/storage.py` persists readings and analytics snapshots.
- `services/analytics.py` computes 24h/7d trends, moving averages, outage signals, volatility, and health scores.
- `services/scheduler.py` uses APScheduler with one job id and `max_instances=1` to avoid duplicate collection jobs.
- `routes/api.py` exposes compatibility and analytics APIs.
- `routes/web.py` serves the dashboard, `robots.txt`, `sitemap.xml`, and favicon.

## Database

Production uses PostgreSQL via `DATABASE_URL`.

Render PostgreSQL usually injects this automatically:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
```

The app normalizes Render `postgres://` URLs to SQLAlchemy-compatible `postgresql+psycopg2://`.

Local fallback is SQLite:

```text
GRID_SQLITE_PATH=data/grid_history.sqlite3
```
=======
- `grid_monitor/__init__.py` creates the Flask app, configures logging, initializes SQLAlchemy and migrations, runs safe startup migrations, registers routes, and starts the scheduler.
- `models.py` defines `grid_snapshots`, `genco_data`, `disco_data`, `analytics_snapshots`, and `distribution_intelligence_snapshots`.
- `services/scraper.py` handles NISO/NIGGRID fetches, parsing, retry logic, timeouts, and source-cache fallback.
- `services/storage.py` persists live readings plus analytics and distribution snapshots.
- `services/analytics.py` computes grid health, moving averages, volatility, outage signals, and GenCo/DisCo analytics.
- `services/distribution.py` computes planning-grade transformer loading estimates from DisCo allocation, regional growth pressure, and historical trend simulation.
- `services/scheduler.py` runs APScheduler collection with `max_instances=1` and `replace_existing=True`.
- `routes/api.py` exposes compatibility, analytics, distribution, metadata, and health endpoints.
- `routes/web.py` serves the dashboard, favicon, robots file, and sitemap.

## Distribution Intelligence

The Distribution Intelligence module is an engineering planning estimate. It does
not claim direct transformer SCADA telemetry. It uses latest DisCo allocation as
a regional load proxy, applies power-factor and utilization assumptions, then
simulates stress under settlement growth.

Outputs include:

- transformer weighted utilization
- overloaded transformer warning classification
- regional risk ranking by DisCo
- simulated utilization trend
- projected 12-month and 36-month settlement growth impact
- recommended planning actions by risk class
>>>>>>> b9a999e (Disable Scheduler for Render deployment)

## API Endpoints

Compatibility endpoints:

- `GET /data`
- `GET /api/grid/live`
- `GET /api/grid/gencos`
- `GET /api/grid/discos`

<<<<<<< HEAD
Analytics platform endpoints:
=======
Platform endpoints:
>>>>>>> b9a999e (Disable Scheduler for Render deployment)

- `GET /api/latest`
- `GET /api/history?hours=24&limit=288`
- `GET /api/analytics?hours=24&limit=288`
<<<<<<< HEAD
=======
- `GET /api/distribution?hours=168&limit=336`
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
- `GET /api/discos`
- `GET /api/gencos`
- `GET /api/metadata`
- `GET /api/health`

Every JSON response includes `response_timestamp`.

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | unset | Render PostgreSQL connection string. |
| `SQLALCHEMY_DATABASE_URI` | unset | Explicit SQLAlchemy URI. |
| `GRID_DATABASE_URL` | unset | Alternate database URI. |
| `GRID_SQLITE_PATH` | `data/grid_history.sqlite3` | Local SQLite fallback path. |
<<<<<<< HEAD
| `APP_BASE_URL` | `https://nigeriapowerdata.com` | Canonical domain for sitemap/robots. |
| `HISTORY_CAPTURE_ENABLED` | `1` | Enables APScheduler collection. |
| `HISTORY_CAPTURE_INTERVAL_SECONDS` | `1800` | 30-minute collection interval. |
| `HISTORY_CAPTURE_ON_STARTUP` | `1` | Captures once when the worker starts. |
| `AUTO_CREATE_TABLES` | `1` | Local convenience fallback. Use migrations in production. |
=======
| `APP_BASE_URL` | `https://nigeriapowerdata.com` | Canonical domain for SEO URLs. |
| `RUN_MIGRATIONS_ON_STARTUP` | `1` | Runs `flask_migrate.upgrade()` during app startup. |
| `AUTO_CREATE_TABLES` | `1` | Local fallback table creation. Set `0` in stricter production environments. |
| `HISTORY_CAPTURE_ENABLED` | `1` | Enables APScheduler collection. |
| `HISTORY_CAPTURE_INTERVAL_SECONDS` | `1800` | 30-minute collection interval. |
| `HISTORY_CAPTURE_ON_STARTUP` | `1` | Captures once when the worker starts. |
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
| `ANALYTICS_CACHE_TTL_SECONDS` | `120` | API analytics cache TTL. |
| `GRID_SOURCE_TIMEOUT_SECONDS` | `12` | Scraper HTTP timeout. |
| `GRID_SCRAPER_RETRIES` | `2` | Scraper retry attempts. |
| `GRID_SCRAPER_BACKOFF_SECONDS` | `1.5` | Linear retry backoff base. |
| `GRID_CACHE_TTL_SECONDS` | `60` | In-memory source cache TTL. |
| `ROLLING_AVERAGE_WINDOW` | `12` | Moving-average reading window. |
| `OUTAGE_DROP_THRESHOLD_PERCENT` | `35` | Sharp-drop outage detection threshold. |
| `OUTAGE_CRITICAL_MW` | `2500` | Critical generation outage threshold. |
<<<<<<< HEAD
=======
| `DISTRIBUTION_POWER_FACTOR` | `0.9` | Power factor assumption for transformer MVA estimates. |
| `TRANSFORMER_BASE_UTILIZATION` | `0.82` | Default transformer planning utilization assumption. |
| `TRANSFORMER_WARNING_UTILIZATION_PERCENT` | `85` | Warning threshold for transformer utilization. |
| `TRANSFORMER_OVERLOAD_UTILIZATION_PERCENT` | `95` | Overload-risk threshold for transformer utilization. |
| `SETTLEMENT_GROWTH_BASE_PERCENT` | `3.8` | Default annual settlement growth assumption for unknown regions. |
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
| `LOG_LEVEL` | `INFO` | Structured logging level. |

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:FLASK_APP = "app.py"
flask db upgrade
python app.py
```

Open:

<<<<<<< HEAD
- Dashboard: http://127.0.0.1:5000/
- Health: http://127.0.0.1:5000/api/health
- Metadata: http://127.0.0.1:5000/api/metadata
=======
- Dashboard: `http://127.0.0.1:5000/`
- Health: `http://127.0.0.1:5000/api/health`
- Metadata: `http://127.0.0.1:5000/api/metadata`
- Distribution intelligence: `http://127.0.0.1:5000/api/distribution`
>>>>>>> b9a999e (Disable Scheduler for Render deployment)

## Migration Commands

Initialize migrations only once, if the `migrations/` folder does not exist:

```powershell
$env:FLASK_APP = "app.py"
flask db init
```

Create a migration after model changes:

```powershell
$env:FLASK_APP = "app.py"
$env:AUTO_CREATE_TABLES = "0"
flask db migrate -m "describe schema change"
```

<<<<<<< HEAD
Apply migrations:
=======
Apply migrations manually:
>>>>>>> b9a999e (Disable Scheduler for Render deployment)

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
```

<<<<<<< HEAD
=======
The app also runs `upgrade()` safely inside `app.app_context()` at startup when
`RUN_MIGRATIONS_ON_STARTUP=1`, which supports Render free-tier deployments
without shell access.

>>>>>>> b9a999e (Disable Scheduler for Render deployment)
## Render Deployment

1. Create or attach a Render PostgreSQL database.
2. Ensure the web service has `DATABASE_URL`.
3. Set `APP_BASE_URL=https://nigeriapowerdata.com`.
4. Keep one Gunicorn worker while APScheduler runs in-process.
<<<<<<< HEAD
5. Push to GitHub and redeploy.
=======
5. Keep `RUN_MIGRATIONS_ON_STARTUP=1` so migrations apply automatically.
6. Push to GitHub and redeploy.
>>>>>>> b9a999e (Disable Scheduler for Render deployment)

The included `Procfile` and `render.yaml` run:

```text
<<<<<<< HEAD
flask --app app.py db upgrade && gunicorn app:app --workers 1 --threads 4 --timeout 75 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:$PORT
```

One worker prevents duplicate APScheduler jobs. If you later scale web workers, move the scheduler into a separate Render worker service or external cron.

## SEO And AdSense Prep

- `robots.txt` and `sitemap.xml` are served from Flask.
- Canonical URL points to `https://nigeriapowerdata.com/`.
- The dashboard contains non-intrusive ad placeholders for future Google AdSense:
  - sidebar slot
  - in-content responsive slot
  - footer banner slot

## Recommended Next Improvements

- Move scheduled ingestion into a dedicated Render worker when traffic grows.
- Add parser fixture tests using saved NIGGRID HTML samples.
- Add uptime monitoring for `/api/health`.
- Add admin-only manual capture endpoint protected by auth.
- Add daily rollup tables once historical data grows.
=======
gunicorn app:app --workers 1 --threads 4 --timeout 75 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:$PORT
```

One worker prevents duplicate APScheduler jobs. If you later scale web workers,
move collection into a separate Render worker or external cron.

## SEO And AdSense Prep

- Canonical URL points to `https://nigeriapowerdata.com/`.
- OpenGraph and Twitter metadata are included.
- `robots.txt` and `sitemap.xml` are served by Flask.
- The dashboard uses semantic sections, accessible labels, responsive cards, and lightweight assets.
- AdSense-safe placeholders exist for sidebar, in-content, and footer inventory.

## Recommended Next Improvements

- Move scheduled ingestion to a dedicated Render worker when traffic grows.
- Add parser fixture tests using saved NIGGRID HTML samples.
- Add admin-only manual capture and backfill endpoints protected by auth.
- Add daily rollup tables once history grows beyond free-tier comfort.
- Add uptime monitoring against `/api/health`.
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
