# Nigeria Power Grid Monitor

Production-grade Flask analytics platform for live and historical Nigeria power-grid intelligence from NISO/NIGGRID public data.

## Current Capabilities

- Live generation scrape from NISO/NIGGRID.
- PostgreSQL persistence through SQLAlchemy, with SQLite fallback for local development.
- 5-minute background history capture.
- Duplicate-safe storage keyed by source reading timestamp.
- GenCo and DisCo records stored per grid snapshot.
- 24-hour trend, moving average, highest and lowest generation metrics.
- Advanced analytics: generation volatility, supply stability score, DisCo load concentration, top GenCos, and grid health classification.
- Structured JSON logs, retrying scraper, source timeout protection, stale fallback responses, and health metadata.
- Responsive dashboard with loading states, error handling, trend arrows, stress indicators, and improved chart rendering.

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
│   │   ├── scheduler.py
│   │   ├── scraper.py
│   │   ├── storage.py
│   │   └── validation.py
│   ├── static/
│   │   ├── css/dashboard.css
│   │   └── js/dashboard.js
│   ├── templates/index.html
│   └── utils/
│       ├── logging.py
│       └── time.py
├── Procfile
├── render.yaml
├── requirements.txt
└── runtime.txt
```

## Architecture

The app uses a Flask application factory in `grid_monitor/__init__.py`.

- `routes/` exposes web and REST endpoints.
- `services/scraper.py` fetches and parses NISO/NIGGRID pages with retries and cache fallback.
- `services/storage.py` persists snapshots, GenCo data, and DisCo data with SQLAlchemy.
- `services/analytics.py` calculates historical and operational metrics.
- `services/scheduler.py` runs the lightweight 5-minute capture loop.
- `models.py` defines `grid_snapshots`, `genco_data`, and `disco_data`.
- Static dashboard assets live under `grid_monitor/static`.

## Database

Preferred production database:

```text
PostgreSQL on Render
```

Set one of:

- `DATABASE_URL`
- `SQLALCHEMY_DATABASE_URI`
- `GRID_DATABASE_URL`

Render PostgreSQL usually injects `DATABASE_URL` automatically after attaching a database to the web service. The app normalizes Render-style `postgres://` URLs for SQLAlchemy.

Local fallback:

```text
sqlite:///data/grid_history.sqlite3
```

Tables are created automatically at startup with `db.create_all()`.

## API Endpoints

Existing compatibility endpoints:

- `GET /data`
- `GET /api/grid/live`
- `GET /api/grid/gencos`
- `GET /api/grid/discos`

Primary platform endpoints:

- `GET /api/latest`
- `GET /api/history?hours=24&limit=288`
- `GET /api/analytics?hours=24&limit=288`
- `GET /api/discos`
- `GET /api/gencos`
- `GET /api/metadata`
- `GET /api/health`

Every JSON response includes `response_timestamp`. Errors use a consistent shape:

```json
{
  "error": "Message",
  "code": "source_unavailable",
  "status": 503,
  "response_timestamp": "2026-05-19T00:00:00+00:00"
}
```

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | unset | Render PostgreSQL connection string. |
| `SQLALCHEMY_DATABASE_URI` | unset | Explicit SQLAlchemy database URI. |
| `GRID_DATABASE_URL` | unset | Alternative database URI. |
| `GRID_SQLITE_PATH` | `data/grid_history.sqlite3` | Local SQLite fallback path. |
| `HISTORY_CAPTURE_ENABLED` | `1` | Enables background capture. |
| `HISTORY_CAPTURE_INTERVAL_SECONDS` | `300` | Capture interval. Minimum is 60 seconds. |
| `HISTORY_CAPTURE_ON_STARTUP` | `1` | Runs one capture when the worker starts. |
| `GRID_SOURCE_TIMEOUT_SECONDS` | `12` | Scraper HTTP timeout. |
| `GRID_SCRAPER_RETRIES` | `2` | Scraper retry attempts. |
| `GRID_SCRAPER_BACKOFF_SECONDS` | `1.5` | Retry backoff base. |
| `GRID_CACHE_TTL_SECONDS` | `60` | In-memory source cache TTL. |
| `ROLLING_AVERAGE_WINDOW` | `12` | Moving-average reading window. |
| `LOG_LEVEL` | `INFO` | Logging level. |

## Local Setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open:

- Dashboard: http://127.0.0.1:5000/
- Health: http://127.0.0.1:5000/api/health
- Metadata: http://127.0.0.1:5000/api/metadata

## Render Deployment

The included `Procfile` and `render.yaml` use:

```text
gunicorn app:app --workers 1 --threads 4 --timeout 75 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:$PORT
```

One worker is intentional because the app has one background capture loop. Use more workers only if capture is moved to a separate worker service or external scheduler.

## Migration Steps From SQLite MVP

1. Add a Render PostgreSQL database.
2. Attach it to the existing Render web service so `DATABASE_URL` is available.
3. Deploy this code.
4. Confirm `/api/health` shows a PostgreSQL database URI and `database.ok: true`.
5. Wait for the first scheduled capture or call `/api/latest` to bootstrap a live snapshot if storage is empty.

Existing SQLite history is not automatically copied to PostgreSQL. For long-term continuity, export old SQLite rows and import them into `grid_snapshots`, `genco_data`, and `disco_data` before switching production traffic.

## Production Notes

- The live endpoint still scrapes NIGGRID directly and preserves its response fields.
- If the upstream source fails, endpoints return cached data or the latest stored snapshot with `stale: true` where possible.
- If both source and storage are empty, source-backed endpoints return `503`.
- Structured logs are emitted as JSON for Render log streams.
- `db.create_all()` keeps deployment simple. For stricter schema evolution later, add Alembic/Flask-Migrate.

## Recommended Next Improvements

- Move the capture loop into a separate Render worker or external cron once traffic grows.
- Add Alembic migrations before making frequent schema changes.
- Add auth/rate limiting for any non-public admin endpoints.
- Add alerting on `/api/health` and capture failure logs.
- Add tests around parser fixtures from NIGGRID HTML snapshots.
- Add a retention policy or rollups once historical storage grows.
