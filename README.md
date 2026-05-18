# Nigeria Power Grid Monitor

Flask dashboard that replaces the simulated generation value with live public grid data from NISO/NIGGRID.

## Data Sources

- Realtime generation, GenCo output, daily peak/off-peak and energy totals: https://www.niggrid.org/Dashboard
- DisCo load allocation profile: https://www.niggrid.org/DisCoLoadProfile

The backend caches source pages for 60 seconds so the dashboard can refresh without hammering NIGGRID.

## Run Locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open:

- Dashboard: http://127.0.0.1:5000/
- Legacy JSON endpoint: http://127.0.0.1:5000/data
- Full live endpoint: http://127.0.0.1:5000/api/grid/live

## Deploy On Render

Push these files to GitHub, then create or update the Render web service from that repository. Render can use either the included `render.yaml` or this `Procfile`:

```text
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

Render should install `requirements.txt`, then start the web service with that Procfile command.

If the app is already connected to Render, commit and push these files, then trigger a redeploy.
