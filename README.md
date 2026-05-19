# Nigeria Power Grid Monitor

Production-minded Flask dashboard for live and historical Nigeria power-grid intelligence from NISO/NIGGRID public data.

## What It Provides

- Live national generation from NIGGRID.
- SQLite-backed historical storage captured every 5 minutes.
- Duplicate-safe snapshot inserts keyed by source reading timestamp.
- Stored GenCo output and DisCo allocation details per snapshot.
- 24-hour generation trend, rolling average, highest stored generation, and lowest stored generation.
- Responsive dashboard with loading, stale fallback, and error states.
- Structured JSON logs for source fetches, history capture, and failures.

## Data Sources

- Realtime generation, GenCo output, daily peak/off-peak, and energy totals: https://www.niggrid.org/Dashboard
- DisCo load allocation profile: https://www.niggrid.org/DisCoLoadProfile

The backend caches source pages briefly to avoid hammering NIGGRID while the UI refreshes.

## API Endpoints

Existing endpoints are preserved:

- `GET /data`
- `GET /api/grid/live`
- `GET /api/grid/gencos`
- `GET /api/grid/discos`

New endpoints:

- `GET /api/latest` - latest stored snapshot, with live bootstrap if storage is empty.
- `GET /api/history?hours=24&limit=288` - historical points and analytics.
- `GET /api/discos` - latest stored DisCo allocation profile.
- `GET /api/gencos` - latest stored GenCo output list.
- `GET /api/health` - database, capture, and scraper health metadata.

## Run Locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open:

- Dashboard: http://127.0.0.1:5000/
- Live JSON: http://127.0.0.1:5000/api/grid/live
- History JSON: http://127.0.0.1:5000/api/history
- Health JSON: http://127.0.0.1:5000/api/health

## SQLite Storage

Default database path:

```text
data/grid_history.sqlite3
```

The app creates the database and tables automatically at startup. Generated database files are intentionally ignored by git.

Stored tables:

- `grid_snapshots`
- `disco_allocations`
- `genco_outputs`

## Environment Variables

All variables are optional.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GRID_DB_PATH` | `data/grid_history.sqlite3` | SQLite database location. |
| `GRID_DATA_DIR` | `data` | Default parent directory when `GRID_DB_PATH` is not set. |
| `HISTORY_CAPTURE_ENABLED` | `1` | Enables the background capture loop. Use `0` to disable. |
| `HISTORY_CAPTURE_INTERVAL_SECONDS` | `300` | Capture interval. Minimum enforced value is 60 seconds. |
| `GRID_SOURCE_TIMEOUT_SECONDS` | `12` | HTTP timeout for NIGGRID requests. |
| `GRID_SCRAPER_RETRIES` | `2` | Number of scraper attempts before falling back. |
| `GRID_SCRAPER_BACKOFF_SECONDS` | `1.5` | Linear retry backoff base in seconds. |
| `GRID_CACHE_TTL_SECONDS` | `60` | In-memory source cache TTL. |
| `ROLLING_AVERAGE_WINDOW` | `12` | Number of stored readings in rolling average. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

## Deploy On Render

Push to GitHub and let Render redeploy the connected web service. The included `render.yaml` and `Procfile` use:

```text
gunicorn app:app --workers 1 --threads 2 --timeout 60 --bind 0.0.0.0:$PORT
```

One worker is intentional because the app runs one lightweight background capture loop. Duplicate database inserts are also prevented by a unique reading timestamp.

Render free-tier note: SQLite files on the free ephemeral filesystem can survive while the instance is running, but they are not durable across service restarts, redeploys, or instance replacement. For durable long-term history on Render, attach a persistent disk or migrate the same storage interface to Postgres later.

## Production Notes

- The live API returns the current scraper payload when NIGGRID is reachable.
- If the source fails after a successful scrape, cached data or the latest stored snapshot can be returned with `stale: true`.
- If storage is empty and the upstream source is unavailable, live endpoints return `503`.
- The dashboard auto-refreshes every 60 seconds; historical capture runs every 5 minutes by default.
