# Nigeria Power Data

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
- Clickable DisCo and GenCo drill-down pages with historical trends, forecasts, risk indicators, utilization charts, rankings, and automated analysis summaries.
- State Intelligence for all 36 Nigerian states plus FCT, including responsible DisCos, estimated allocation, peak demand, settlement growth, infrastructure stress, transformer risk, reliability, and peer ranking.
- Regional Intelligence across the six geopolitical zones with aggregate state trends and DisCo coverage.
- Hierarchical Geographic Intelligence map with State to LGA to Town/City to Community to Settlement drill-down, direct search, demand estimates, transformer loading, grid health, and upgrade recommendations.
- Public content pages for About, Contact, Privacy Policy, Terms of Use, Methodology, and Data Sources.
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
|   |   |-- entity_intelligence.py
|   |   |-- geographic_hierarchy.py
|   |   |-- state_intelligence.py
|   |   |-- scheduler.py
|   |   |-- scraper.py
|   |   |-- storage.py
|   |   `-- validation.py
|   |-- static/
|   |   |-- css/dashboard.css
|   |   |-- js/dashboard.js
|   |   |-- js/entity.js
|   |   |-- js/geo.js
|   |   |-- js/hierarchy.js
|   |   |-- favicon.svg
|   |   `-- logo.svg
|   |-- templates/
|   |   |-- entity.html
|   |   |-- geo.html
|   |   |-- geo_index.html
|   |   |-- hierarchy_detail.html
|   |   |-- hierarchy_index.html
|   |   |-- index.html
|   |   `-- page.html
|   `-- utils/
|       |-- logging.py
|       `-- time.py
|-- migrations/
|   `-- versions/
|-- Procfile
|-- gunicorn.conf.py
|-- render.yaml
|-- requirements.txt
`-- runtime.txt
```

## Architecture

- `grid_monitor/__init__.py` creates the Flask app, configures logging, initializes SQLAlchemy and migrations, runs safe startup migrations, registers routes, and can start the scheduler when explicitly enabled.
- `app.py` exposes `app` for Gunicorn and falls back to a minimal health app if a production-only startup exception occurs.
- `models.py` defines `grid_snapshots`, `genco_data`, `disco_data`, `analytics_snapshots`, and `distribution_intelligence_snapshots`.
- `services/scraper.py` handles NISO/NIGGRID fetches, parsing, retry logic, timeouts, and source-cache fallback.
- `services/storage.py` persists live readings plus analytics and distribution snapshots.
- `services/analytics.py` computes grid health, moving averages, volatility, outage signals, and GenCo/DisCo analytics.
- `services/distribution.py` computes planning-grade transformer loading estimates from DisCo allocation, regional growth pressure, and historical trend simulation.
- `services/entity_intelligence.py` resolves DisCo/GenCo slugs and builds entity-level history, forecasts, rankings, risk, utilization, and generated analysis summaries.
- `services/state_intelligence.py` maps states and regions to responsible DisCos and estimates geography-level allocation, demand, reliability, stress, transformer risk, and peer rankings.
- `services/geographic_hierarchy.py` builds the replaceable State/LGA/Town/Community/Settlement hierarchy, search index, map payload, demand estimates, transformer loading, grid health, and infrastructure upgrade recommendations.
- `services/scheduler.py` runs APScheduler collection with `max_instances=1` and `replace_existing=True` when `WEB_SCHEDULER_ENABLED=1`.
- `routes/api.py` exposes compatibility, analytics, distribution, metadata, and health endpoints.
- `routes/web.py` serves the dashboard, entity drill-down pages, state and regional intelligence pages, hierarchical map pages, content pages, favicon, robots file, and sitemap.

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

## State And Regional Intelligence

State and regional intelligence is a planning estimate layered on top of DisCo
allocation readings. It maps each state and FCT to one or more responsible DisCos
using public franchise-area coverage, then apportions latest and historical
DisCo allocation into geography-level signals.

Outputs include:

- responsible DisCo or DisCos
- estimated current allocation
- historical allocation trend and moving average
- estimated peak demand and demand growth
- population served estimate
- settlement growth indicator
- infrastructure stress, transformer risk, grid reliability, and availability scores
- state or regional peer rankings
- automated planning-grade analysis summary

## Hierarchical Geographic Intelligence

The Geographic Intelligence map is data-driven and uses planning-grade seed
records by default. It currently generates a consistent hierarchy from state
profiles and representative LGA, town/city, community, and settlement planning
areas. Future official datasets can replace these placeholders by providing a
JSON node list through `GEOGRAPHY_DATASET_PATH`; the API payloads and UI remain
the same.

Outputs include:

- interactive Nigeria state map
- direct search across state, LGA, town/city, community, and settlement nodes
- estimated population, current demand, and peak demand
- projected 12-month and 36-month demand
- transformer loading and grid health classification
- DisCo coverage inherited from state franchise-area mapping
- recommended infrastructure upgrades based on loading, growth, and data quality

## API Endpoints

Compatibility endpoints:

- `GET /data`
- `GET /api/grid/live`
- `GET /api/grid/gencos`
- `GET /api/grid/discos`

Platform endpoints:

- `GET /api/latest`
- `GET /api/market-data`
- `GET /api/generation?hours=24&limit=288`
- `GET /api/history?hours=24&limit=288`
- `GET /api/analytics?hours=24&limit=288`
- `GET /api/distribution?hours=168&limit=336`
- `GET /api/discos`
- `GET /api/discos/{slug}?hours=168&limit=1000`
- `GET /api/gencos`
- `GET /api/gencos/{slug}?hours=168&limit=1000`
- `GET /api/entities`
- `GET /api/states`
- `GET /api/states/{slug}?hours=168&limit=1000`
- `GET /api/regions`
- `GET /api/regions/{slug}?hours=168&limit=1000`
- `GET /api/geography/map`
- `GET /api/geography/search?q=lagos`
- `GET /api/geography/{level}/{slug}`
- `GET /api/metadata`
- `GET /api/health`

Every JSON response includes `response_timestamp`.

Web pages:

- `/discos/{slug}`
- `/gencos/{slug}`
- `/states`
- `/state/{slug}`
- `/regions`
- `/region/{slug}`
- `/geography`
- `/geography/{level}/{slug}`
- `/about`
- `/contact`
- `/privacy-policy`
- `/terms-of-use`
- `/methodology`
- `/data-sources`

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | unset | Render PostgreSQL connection string. |
| `SQLALCHEMY_DATABASE_URI` | unset | Explicit SQLAlchemy URI. |
| `GRID_DATABASE_URL` | unset | Alternate database URI. |
| `POSTGRES_DRIVER` | `psycopg` | PostgreSQL SQLAlchemy driver for normalized Render URLs. |
| `GRID_SQLITE_PATH` | `data/grid_history.sqlite3` | Local SQLite fallback path. |
| `APP_BASE_URL` | `https://nigeriapowerdata.com` | Canonical domain for SEO URLs. |
| `CONTACT_EMAIL` | `hello@nigeriapowerdata.com` | Public general contact email shown on About and Contact pages. |
| `RESEARCH_EMAIL` | `CONTACT_EMAIL` | Research collaboration and data-correction email. |
| `ADS_EMAIL` | `CONTACT_EMAIL` | Advertising and sponsorship enquiry email. |
| `GEOGRAPHY_DATASET_PATH` | unset | Optional JSON node dataset for replacing built-in hierarchy planning seeds. |
| `RUN_MIGRATIONS_ON_STARTUP` | `1` | Runs Alembic migrations during app startup. |
| `REQUIRE_DATABASE_ON_STARTUP` | `0` | Set `1` only if Gunicorn should fail when the database is unavailable. |
| `STARTUP_ERROR_DEBUG` | `0` | Adds a traceback tail to fallback `/api/health` responses for temporary deployment debugging. |
| `AUTO_CREATE_TABLES` | `1` | Local fallback table creation. Set `0` in stricter production environments. |
| `HISTORY_CAPTURE_ENABLED` | `1` | Enables APScheduler collection. |
| `WEB_SCHEDULER_ENABLED` | auto on Render/PostgreSQL | Starts APScheduler inside the web process. Set `0` only for local development or external scheduler setups. |
| `HISTORY_CAPTURE_INTERVAL_SECONDS` | `1800` | 30-minute collection interval. |
| `HISTORY_CAPTURE_ON_STARTUP` | `1` | Captures once when the worker starts. |
| `ANALYTICS_CACHE_TTL_SECONDS` | `120` | API analytics cache TTL. |
| `GRID_SOURCE_TIMEOUT_SECONDS` | `12` | Scraper HTTP timeout. |
| `GRID_SCRAPER_RETRIES` | `2` | Scraper retry attempts. |
| `GRID_SCRAPER_BACKOFF_SECONDS` | `1.5` | Linear retry backoff base. |
| `GRID_CACHE_TTL_SECONDS` | `60` | In-memory source cache TTL. |
| `ROLLING_AVERAGE_WINDOW` | `12` | Moving-average reading window. |
| `OUTAGE_DROP_THRESHOLD_PERCENT` | `35` | Sharp-drop outage detection threshold. |
| `OUTAGE_CRITICAL_MW` | `2500` | Critical generation outage threshold. |
| `DISTRIBUTION_POWER_FACTOR` | `0.9` | Power factor assumption for transformer MVA estimates. |
| `TRANSFORMER_BASE_UTILIZATION` | `0.82` | Default transformer planning utilization assumption. |
| `TRANSFORMER_WARNING_UTILIZATION_PERCENT` | `85` | Warning threshold for transformer utilization. |
| `TRANSFORMER_OVERLOAD_UTILIZATION_PERCENT` | `95` | Overload-risk threshold for transformer utilization. |
| `SETTLEMENT_GROWTH_BASE_PERCENT` | `3.8` | Default annual settlement growth assumption for unknown regions. |
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

- Dashboard: `http://127.0.0.1:5000/`
- Health: `http://127.0.0.1:5000/api/health`
- Metadata: `http://127.0.0.1:5000/api/metadata`
- Distribution intelligence: `http://127.0.0.1:5000/api/distribution`

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

Apply migrations manually:

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
```

The app also runs Alembic upgrade safely inside `app.app_context()` at startup when
`RUN_MIGRATIONS_ON_STARTUP=1`, which supports Render free-tier deployments
without shell access.

## Render Deployment

1. Create or attach a Render PostgreSQL database.
2. Ensure the web service has `DATABASE_URL`.
3. Set `APP_BASE_URL=https://nigeriapowerdata.com`.
4. Keep `WEB_SCHEDULER_ENABLED=0` on the web service unless you intentionally run collection inside the web process.
5. Keep `RUN_MIGRATIONS_ON_STARTUP=1` so migrations apply automatically.
6. Keep `REQUIRE_DATABASE_ON_STARTUP=0` so a transient database problem does not kill the web worker during deploy.
7. Push to GitHub and redeploy.

The included `Procfile` and `render.yaml` run:

```text
gunicorn app:app
```

Gunicorn reads `gunicorn.conf.py`, which binds to `0.0.0.0:$PORT`, keeps one
worker by default, and sets thread/timeout/restart limits safely for Render.
`WEB_SCHEDULER_ENABLED=0` prevents duplicate in-process collection on the web
service. Startup migrations use Alembic directly and stamp recoverable legacy
states, so a stale `alembic_version` value cannot terminate Gunicorn during
module import. Run collection from a separate Render worker or external cron
when you are ready to automate ingestion again.

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
