# Nigeria Power Data

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
```

## Architecture

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

## API Endpoints

Compatibility endpoints:

- `GET /data`
- `GET /api/grid/live`
- `GET /api/grid/gencos`
- `GET /api/grid/discos`

Analytics platform endpoints:

- `GET /api/latest`
- `GET /api/history?hours=24&limit=288`
- `GET /api/analytics?hours=24&limit=288`
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
| `APP_BASE_URL` | `https://nigeriapowerdata.com` | Canonical domain for sitemap/robots. |
| `HISTORY_CAPTURE_ENABLED` | `1` | Enables APScheduler collection. |
| `HISTORY_CAPTURE_INTERVAL_SECONDS` | `1800` | 30-minute collection interval. |
| `HISTORY_CAPTURE_ON_STARTUP` | `1` | Captures once when the worker starts. |
| `AUTO_CREATE_TABLES` | `1` | Local convenience fallback. Use migrations in production. |
| `ANALYTICS_CACHE_TTL_SECONDS` | `120` | API analytics cache TTL. |
| `GRID_SOURCE_TIMEOUT_SECONDS` | `12` | Scraper HTTP timeout. |
| `GRID_SCRAPER_RETRIES` | `2` | Scraper retry attempts. |
| `GRID_SCRAPER_BACKOFF_SECONDS` | `1.5` | Linear retry backoff base. |
| `GRID_CACHE_TTL_SECONDS` | `60` | In-memory source cache TTL. |
| `ROLLING_AVERAGE_WINDOW` | `12` | Moving-average reading window. |
| `OUTAGE_DROP_THRESHOLD_PERCENT` | `35` | Sharp-drop outage detection threshold. |
| `OUTAGE_CRITICAL_MW` | `2500` | Critical generation outage threshold. |
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

- Dashboard: http://127.0.0.1:5000/
- Health: http://127.0.0.1:5000/api/health
- Metadata: http://127.0.0.1:5000/api/metadata

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

Apply migrations:

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
```

## Render Deployment

1. Create or attach a Render PostgreSQL database.
2. Ensure the web service has `DATABASE_URL`.
3. Set `APP_BASE_URL=https://nigeriapowerdata.com`.
4. Keep one Gunicorn worker while APScheduler runs in-process.
5. Push to GitHub and redeploy.

The included `Procfile` and `render.yaml` run:

```text
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
