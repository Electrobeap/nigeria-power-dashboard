import atexit
import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("GRID_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.environ.get("GRID_DB_PATH", os.path.join(DATA_DIR, "grid_history.sqlite3"))

NIGGRID_DASHBOARD_URL = "https://www.niggrid.org/Dashboard"
NIGGRID_DISCO_URL = "https://www.niggrid.org/DisCoLoadProfile"
NIGERIA_TZ = timezone(timedelta(hours=1), "WAT")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


REQUEST_TIMEOUT_SECONDS = _env_float("GRID_SOURCE_TIMEOUT_SECONDS", 12.0)
SCRAPER_RETRIES = max(1, _env_int("GRID_SCRAPER_RETRIES", 2))
SCRAPER_BACKOFF_SECONDS = _env_float("GRID_SCRAPER_BACKOFF_SECONDS", 1.5)
CACHE_TTL_SECONDS = _env_int("GRID_CACHE_TTL_SECONDS", 60)
HISTORY_CAPTURE_INTERVAL_SECONDS = max(
    60, _env_int("HISTORY_CAPTURE_INTERVAL_SECONDS", 300)
)
HISTORY_CAPTURE_ENABLED = _env_bool("HISTORY_CAPTURE_ENABLED", True)
ROLLING_AVERAGE_WINDOW = max(1, _env_int("ROLLING_AVERAGE_WINDOW", 12))

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(message)s")
logger = logging.getLogger("grid_monitor")
logger.setLevel(LOG_LEVEL)

_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()
_capture_lock = threading.Lock()
_capture_stop = threading.Event()
_capture_started = False


class SourceUnavailable(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, "timestamp": _now_iso(), **fields}
    logger.log(level, json.dumps(payload, default=str, sort_keys=True))


def _copy_jsonable(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, default=str))


def _cached(key: str, loader):
    current_ts = datetime.now(timezone.utc).timestamp()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and current_ts - cached["loaded_at"] < CACHE_TTL_SECONDS:
            return _copy_jsonable(cached["value"])

    try:
        value = loader()
    except Exception as exc:
        with _cache_lock:
            cached = _cache.get(key)
        if cached:
            stale = _copy_jsonable(cached["value"])
            stale["stale"] = True
            stale["stale_age_seconds"] = round(current_ts - cached["loaded_at"])
            stale["source_error"] = str(exc)
            _log_event(
                logging.WARNING,
                "cache_stale_fallback",
                cache_key=key,
                stale_age_seconds=stale["stale_age_seconds"],
                error=str(exc),
            )
            return stale
        raise

    with _cache_lock:
        _cache[key] = {"loaded_at": current_ts, "value": value}
    return _copy_jsonable(value)


def _fetch_text(url: str) -> str:
    headers = {
        "User-Agent": (
            "NigeriaPowerDashboard/1.0 "
            "(public grid statistics scraper; contact site owner if blocked)"
        )
    }
    last_error: Exception | None = None
    for attempt in range(1, SCRAPER_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            _log_event(
                logging.INFO,
                "source_fetch_ok",
                url=url,
                attempt=attempt,
                status_code=response.status_code,
            )
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            _log_event(
                logging.WARNING,
                "source_fetch_failed",
                url=url,
                attempt=attempt,
                max_attempts=SCRAPER_RETRIES,
                error=str(exc),
            )
            if attempt < SCRAPER_RETRIES:
                time.sleep(SCRAPER_BACKOFF_SECONDS * attempt)

    raise SourceUnavailable(f"Could not fetch NIGGRID source after retries: {last_error}")


def _clean_number(value: str) -> float:
    return float(value.replace(",", "").strip())


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def _extract_realtime(text: str) -> dict[str, Any]:
    match = re.search(
        r"Realtime Generation\s*::\s*as at\s*(?P<time>\d{1,2}:\d{2})\s*is\s*"
        r"(?P<mw>[\d,.]+)\s*MW\s*as reported by\s*(?P<count>\d+)\s*Gencos",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise SourceUnavailable("Could not parse realtime generation from NIGGRID.")

    return {
        "as_at_time": match.group("time"),
        "total_generation_mw": _clean_number(match.group("mw")),
        "reporting_gencos": int(match.group("count")),
    }


def _extract_daily_performance(text: str) -> dict[str, Any]:
    date_match = re.search(
        r"Per(?:for|fro)mance For\s*::\s*(?P<date>\d{2}/\d{2}/\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    peak_match = re.search(
        r"Peak\s+Generation\s+(?P<mw>[\d,.]+)\s*MW\s+Time:\s*"
        r"(?P<time>[^|]+)\|\s*Freq\.:\s*(?P<freq>[\d.]+)\s*Hz",
        text,
        flags=re.IGNORECASE,
    )
    off_peak_match = re.search(
        r"Off-Peak\s+Generation\s+(?P<mw>[\d,.]+)\s*MW\s+Time:\s*"
        r"(?P<time>[^|]+)\|\s*Freq\.:\s*(?P<freq>[\d.]+)\s*Hz",
        text,
        flags=re.IGNORECASE,
    )
    energy_generated_match = re.search(
        r"Energy\s+Generated\s+(?P<mwh>[\d,.]+)\s*MWh",
        text,
        flags=re.IGNORECASE,
    )
    energy_sent_match = re.search(
        r"Energy\s+Sent Out\s+(?P<mwh>[\d,.]+)\s*MWh",
        text,
        flags=re.IGNORECASE,
    )

    return {
        "performance_date": date_match.group("date") if date_match else None,
        "peak_generation_mw": _clean_number(peak_match.group("mw")) if peak_match else None,
        "peak_time": peak_match.group("time").strip() if peak_match else None,
        "peak_frequency_hz": _clean_number(peak_match.group("freq")) if peak_match else None,
        "off_peak_generation_mw": (
            _clean_number(off_peak_match.group("mw")) if off_peak_match else None
        ),
        "off_peak_time": off_peak_match.group("time").strip() if off_peak_match else None,
        "off_peak_frequency_hz": (
            _clean_number(off_peak_match.group("freq")) if off_peak_match else None
        ),
        "energy_generated_mwh": (
            _clean_number(energy_generated_match.group("mwh"))
            if energy_generated_match
            else None
        ),
        "energy_sent_out_mwh": (
            _clean_number(energy_sent_match.group("mwh")) if energy_sent_match else None
        ),
    }


def _extract_gencos(text: str) -> list[dict[str, Any]]:
    start = text.find("Gencos")
    end = text.find("date_range", start)
    if start == -1 or end == -1:
        raise SourceUnavailable("Could not locate GenCo table on NIGGRID.")

    block = text[start + len("Gencos") : end]
    plants = re.findall(
        r"\b\d{1,2}\s+(.+?)\s+(\d[\d,.]*)\s+(?=\d{1,2}\s+|$)",
        block,
    )
    return [
        {"plant": plant.strip(), "generation_mw": _clean_number(mw)}
        for plant, mw in plants
    ]


def _load_dashboard() -> dict[str, Any]:
    html = _fetch_text(NIGGRID_DASHBOARD_URL)
    text = _page_text(html)
    realtime = _extract_realtime(text)

    return {
        **realtime,
        "daily": _extract_daily_performance(text),
        "gencos": _extract_gencos(text),
        "source": "NISO NIGGRID 24hr Grid Performance Dashboard",
        "source_url": NIGGRID_DASHBOARD_URL,
        "fetched_at": _now_iso(),
    }


def _load_disco_profile() -> dict[str, Any]:
    html = _fetch_text(NIGGRID_DISCO_URL)
    text = _page_text(html)

    as_at_match = re.search(
        r"Distribution Load Profile Data as at\s+(.+?)\s+Company Load Allocation",
        text,
        flags=re.IGNORECASE,
    )
    block_match = re.search(
        r"Company Load Allocation \(MW\)\s+(.+?)\s+Total:\s+([\d,.]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not block_match:
        raise SourceUnavailable("Could not parse DisCo load profile from NIGGRID.")

    entries = re.findall(r"([A-Za-z]+(?:\s+[A-Za-z]+)*)\s+([\d,.]+)", block_match.group(1))
    return {
        "as_at": as_at_match.group(1).strip() if as_at_match else None,
        "discos": [
            {"company": company.strip(), "load_allocation_mw": _clean_number(mw)}
            for company, mw in entries
        ],
        "total_load_allocation_mw": _clean_number(block_match.group(2)),
        "source": "NISO NIGGRID DISCOs Load Profile",
        "source_url": NIGGRID_DISCO_URL,
        "fetched_at": _now_iso(),
    }


def _grid_payload() -> dict[str, Any]:
    dashboard = _cached("dashboard", _load_dashboard)
    try:
        disco_profile = _cached("disco_profile", _load_disco_profile)
    except Exception as exc:
        _log_event(logging.WARNING, "disco_profile_fallback_empty", error=str(exc))
        disco_profile = {
            "as_at": None,
            "discos": [],
            "total_load_allocation_mw": None,
            "source": "NISO NIGGRID DISCOs Load Profile",
            "source_url": NIGGRID_DISCO_URL,
            "fetched_at": _now_iso(),
            "error": str(exc),
        }
    return {**dashboard, "disco_profile": disco_profile}


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    if DB_PATH != ":memory:":
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    with _connect_db() as conn:
        if DB_PATH != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS grid_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_timestamp TEXT NOT NULL UNIQUE,
                captured_at TEXT NOT NULL,
                as_at_time TEXT,
                total_generation_mw REAL NOT NULL,
                reporting_gencos INTEGER,
                source TEXT,
                source_url TEXT,
                daily_json TEXT NOT NULL DEFAULT '{}',
                disco_as_at TEXT,
                total_load_allocation_mw REAL,
                raw_payload_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_grid_snapshots_reading_timestamp
                ON grid_snapshots(reading_timestamp);

            CREATE TABLE IF NOT EXISTS disco_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                company TEXT NOT NULL,
                load_allocation_mw REAL,
                FOREIGN KEY(snapshot_id) REFERENCES grid_snapshots(id) ON DELETE CASCADE,
                UNIQUE(snapshot_id, company)
            );

            CREATE INDEX IF NOT EXISTS idx_disco_allocations_snapshot_id
                ON disco_allocations(snapshot_id);

            CREATE TABLE IF NOT EXISTS genco_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                plant TEXT NOT NULL,
                generation_mw REAL,
                FOREIGN KEY(snapshot_id) REFERENCES grid_snapshots(id) ON DELETE CASCADE,
                UNIQUE(snapshot_id, plant)
            );

            CREATE INDEX IF NOT EXISTS idx_genco_outputs_snapshot_id
                ON genco_outputs(snapshot_id);
            """
        )
    _log_event(logging.INFO, "database_initialized", db_path=DB_PATH)


def _source_reading_timestamp(payload: dict[str, Any]) -> str:
    daily = payload.get("daily") or {}
    source_date = daily.get("performance_date")
    source_time = payload.get("as_at_time")
    if source_date and source_time:
        for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
            try:
                local_dt = datetime.strptime(
                    f"{source_date} {source_time.strip()}", fmt
                ).replace(tzinfo=NIGERIA_TZ)
                return local_dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                continue

    fetched_at = payload.get("fetched_at")
    if fetched_at:
        try:
            parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return _now_iso()


def save_grid_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    reading_timestamp = _source_reading_timestamp(payload)
    captured_at = payload.get("fetched_at") or _now_iso()
    disco_profile = payload.get("disco_profile") or {}
    gencos = payload.get("gencos") or []
    discos = disco_profile.get("discos") or []

    with _connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO grid_snapshots (
                reading_timestamp,
                captured_at,
                as_at_time,
                total_generation_mw,
                reporting_gencos,
                source,
                source_url,
                daily_json,
                disco_as_at,
                total_load_allocation_mw,
                raw_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading_timestamp,
                captured_at,
                payload.get("as_at_time"),
                payload.get("total_generation_mw"),
                payload.get("reporting_gencos"),
                payload.get("source"),
                payload.get("source_url"),
                json.dumps(payload.get("daily") or {}, sort_keys=True),
                disco_profile.get("as_at"),
                disco_profile.get("total_load_allocation_mw"),
                json.dumps(payload, sort_keys=True, default=str),
            ),
        )
        if cursor.rowcount == 0:
            row = conn.execute(
                "SELECT id FROM grid_snapshots WHERE reading_timestamp = ?",
                (reading_timestamp,),
            ).fetchone()
            return {
                "inserted": False,
                "snapshot_id": row["id"] if row else None,
                "reading_timestamp": reading_timestamp,
            }

        snapshot_id = cursor.lastrowid
        conn.executemany(
            """
            INSERT OR IGNORE INTO disco_allocations (
                snapshot_id,
                company,
                load_allocation_mw
            )
            VALUES (?, ?, ?)
            """,
            [
                (snapshot_id, row.get("company"), row.get("load_allocation_mw"))
                for row in discos
                if row.get("company")
            ],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO genco_outputs (
                snapshot_id,
                plant,
                generation_mw
            )
            VALUES (?, ?, ?)
            """,
            [
                (snapshot_id, row.get("plant"), row.get("generation_mw"))
                for row in gencos
                if row.get("plant")
            ],
        )

    return {
        "inserted": True,
        "snapshot_id": snapshot_id,
        "reading_timestamp": reading_timestamp,
    }


def _snapshot_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    gencos = conn.execute(
        """
        SELECT plant, generation_mw
        FROM genco_outputs
        WHERE snapshot_id = ?
        ORDER BY generation_mw DESC, plant ASC
        """,
        (row["id"],),
    ).fetchall()
    discos = conn.execute(
        """
        SELECT company, load_allocation_mw
        FROM disco_allocations
        WHERE snapshot_id = ?
        ORDER BY load_allocation_mw DESC, company ASC
        """,
        (row["id"],),
    ).fetchall()

    try:
        daily = json.loads(row["daily_json"] or "{}")
    except json.JSONDecodeError:
        daily = {}

    return {
        "snapshot_id": row["id"],
        "reading_timestamp": row["reading_timestamp"],
        "captured_at": row["captured_at"],
        "as_at_time": row["as_at_time"],
        "total_generation_mw": row["total_generation_mw"],
        "reporting_gencos": row["reporting_gencos"],
        "daily": daily,
        "gencos": [
            {"plant": item["plant"], "generation_mw": item["generation_mw"]}
            for item in gencos
        ],
        "disco_profile": {
            "as_at": row["disco_as_at"],
            "discos": [
                {
                    "company": item["company"],
                    "load_allocation_mw": item["load_allocation_mw"],
                }
                for item in discos
            ],
            "total_load_allocation_mw": row["total_load_allocation_mw"],
            "source": "NISO NIGGRID DISCOs Load Profile",
            "source_url": NIGGRID_DISCO_URL,
            "fetched_at": row["captured_at"],
        },
        "source": row["source"],
        "source_url": row["source_url"],
        "fetched_at": row["captured_at"],
        "stored": True,
    }


def get_latest_snapshot() -> dict[str, Any] | None:
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM grid_snapshots
            ORDER BY reading_timestamp DESC
            LIMIT 1
            """
        ).fetchone()
        return _snapshot_from_row(conn, row) if row else None


def _history_points(hours: float, limit: int) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM (
                SELECT id, reading_timestamp, captured_at, total_generation_mw,
                       reporting_gencos, as_at_time
                FROM grid_snapshots
                WHERE reading_timestamp >= ?
                ORDER BY reading_timestamp DESC
                LIMIT ?
            )
            ORDER BY reading_timestamp ASC
            """,
            (since.isoformat(), limit),
        ).fetchall()

        if not rows:
            rows = conn.execute(
                """
                SELECT id, reading_timestamp, captured_at, total_generation_mw,
                       reporting_gencos, as_at_time
                FROM grid_snapshots
                ORDER BY reading_timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            rows = list(reversed(rows))

    window: list[float] = []
    points: list[dict[str, Any]] = []
    for row in rows:
        mw = float(row["total_generation_mw"])
        window.append(mw)
        if len(window) > ROLLING_AVERAGE_WINDOW:
            window.pop(0)

        points.append(
            {
                "snapshot_id": row["id"],
                "timestamp": row["reading_timestamp"],
                "captured_at": row["captured_at"],
                "as_at_time": row["as_at_time"],
                "total_generation_mw": mw,
                "reporting_gencos": row["reporting_gencos"],
                "rolling_average_mw": round(sum(window) / len(window), 2),
            }
        )
    return points


def _history_analytics(points: list[dict[str, Any]], hours: float) -> dict[str, Any]:
    if not points:
        return {
            "window_hours": hours,
            "sample_count": 0,
            "last_24h_generation_trend": None,
            "rolling_average_mw": None,
            "rolling_average_window_readings": ROLLING_AVERAGE_WINDOW,
            "highest_daily_generation": None,
            "lowest_daily_generation": None,
        }

    first = points[0]
    latest = points[-1]
    delta = latest["total_generation_mw"] - first["total_generation_mw"]
    percent_change = (
        (delta / first["total_generation_mw"]) * 100
        if first["total_generation_mw"]
        else None
    )
    highest = max(points, key=lambda item: item["total_generation_mw"])
    lowest = min(points, key=lambda item: item["total_generation_mw"])

    return {
        "window_hours": hours,
        "sample_count": len(points),
        "last_24h_generation_trend": {
            "from_timestamp": first["timestamp"],
            "to_timestamp": latest["timestamp"],
            "change_mw": round(delta, 2),
            "change_percent": round(percent_change, 2)
            if percent_change is not None
            else None,
            "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
        },
        "rolling_average_mw": latest["rolling_average_mw"],
        "rolling_average_window_readings": ROLLING_AVERAGE_WINDOW,
        "highest_daily_generation": {
            "timestamp": highest["timestamp"],
            "total_generation_mw": highest["total_generation_mw"],
        },
        "lowest_daily_generation": {
            "timestamp": lowest["timestamp"],
            "total_generation_mw": lowest["total_generation_mw"],
        },
    }


def history_payload(hours: float = 24, limit: int = 288) -> dict[str, Any]:
    points = _history_points(hours, limit)
    return {
        "generated_at": _now_iso(),
        "hours": hours,
        "limit": limit,
        "history": points,
        "analytics": _history_analytics(points, hours),
    }


def _bounded_float(value: str | None, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except ValueError:
        parsed = default
    return min(max(parsed, minimum), maximum)


def _bounded_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        parsed = default
    return min(max(parsed, minimum), maximum)


def _capture_once() -> dict[str, Any]:
    payload = _grid_payload()
    result = save_grid_snapshot(payload)
    _log_event(
        logging.INFO,
        "history_capture_complete",
        inserted=result["inserted"],
        snapshot_id=result["snapshot_id"],
        reading_timestamp=result["reading_timestamp"],
    )
    return result


def _capture_loop() -> None:
    _log_event(
        logging.INFO,
        "history_capture_started",
        interval_seconds=HISTORY_CAPTURE_INTERVAL_SECONDS,
    )
    while not _capture_stop.is_set():
        try:
            _capture_once()
        except Exception as exc:
            _log_event(logging.ERROR, "history_capture_failed", error=str(exc))
        _capture_stop.wait(HISTORY_CAPTURE_INTERVAL_SECONDS)


def _should_start_capture_thread() -> bool:
    if not HISTORY_CAPTURE_ENABLED:
        return False
    if os.environ.get("FLASK_DEBUG") == "1" and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def start_history_capture() -> None:
    global _capture_started
    with _capture_lock:
        if _capture_started:
            return
        thread = threading.Thread(
            target=_capture_loop,
            name="grid-history-capture",
            daemon=True,
        )
        thread.start()
        _capture_started = True


def _fallback_latest_response(error: Exception):
    snapshot = get_latest_snapshot()
    if not snapshot:
        return None
    snapshot["stale"] = True
    snapshot["source_error"] = str(error)
    return jsonify(snapshot)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/data")
def legacy_data():
    try:
        data = _grid_payload()
    except Exception as exc:
        fallback = get_latest_snapshot()
        if not fallback:
            return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503
        data = fallback

    return jsonify(
        {
            "total_generation_mw": data["total_generation_mw"],
            "timestamp": data["as_at_time"],
            "source": data["source"],
            "source_url": data["source_url"],
            "fetched_at": data["fetched_at"],
            "reporting_gencos": data["reporting_gencos"],
        }
    )


@app.get("/api/grid/live")
def live_grid():
    try:
        return jsonify(_grid_payload())
    except Exception as exc:
        fallback = _fallback_latest_response(exc)
        if fallback:
            return fallback
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/grid/gencos")
def grid_gencos():
    try:
        data = _cached("dashboard", _load_dashboard)
        return jsonify(
            {
                "gencos": data["gencos"],
                "source": data["source"],
                "source_url": data["source_url"],
                "fetched_at": data["fetched_at"],
                "stale": data.get("stale", False),
            }
        )
    except Exception as exc:
        snapshot = get_latest_snapshot()
        if snapshot and snapshot["gencos"]:
            return jsonify(
                {
                    "gencos": snapshot["gencos"],
                    "source": snapshot["source"],
                    "source_url": snapshot["source_url"],
                    "fetched_at": snapshot["fetched_at"],
                    "reading_timestamp": snapshot["reading_timestamp"],
                    "stale": True,
                    "source_error": str(exc),
                }
            )
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/grid/discos")
def grid_discos():
    try:
        return jsonify(_cached("disco_profile", _load_disco_profile))
    except Exception as exc:
        snapshot = get_latest_snapshot()
        if snapshot and snapshot["disco_profile"]["discos"]:
            profile = snapshot["disco_profile"]
            profile["reading_timestamp"] = snapshot["reading_timestamp"]
            profile["stale"] = True
            profile["source_error"] = str(exc)
            return jsonify(profile)
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/history")
def history():
    hours = _bounded_float(request.args.get("hours"), 24, 1, 168)
    limit = _bounded_int(request.args.get("limit"), 288, 1, 2000)
    return jsonify(history_payload(hours=hours, limit=limit))


@app.get("/api/latest")
def latest():
    snapshot = get_latest_snapshot()
    if snapshot:
        return jsonify(snapshot)

    try:
        live = _grid_payload()
        save_grid_snapshot(live)
        snapshot = get_latest_snapshot()
        return jsonify(snapshot or live)
    except Exception as exc:
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/discos")
def discos():
    snapshot = get_latest_snapshot()
    if snapshot and snapshot["disco_profile"]["discos"]:
        profile = snapshot["disco_profile"]
        profile["reading_timestamp"] = snapshot["reading_timestamp"]
        return jsonify(profile)

    try:
        return jsonify(_cached("disco_profile", _load_disco_profile))
    except Exception as exc:
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/gencos")
def gencos():
    snapshot = get_latest_snapshot()
    if snapshot and snapshot["gencos"]:
        return jsonify(
            {
                "gencos": snapshot["gencos"],
                "source": snapshot["source"],
                "source_url": snapshot["source_url"],
                "fetched_at": snapshot["fetched_at"],
                "reading_timestamp": snapshot["reading_timestamp"],
            }
        )

    try:
        data = _cached("dashboard", _load_dashboard)
        return jsonify(
            {
                "gencos": data["gencos"],
                "source": data["source"],
                "source_url": data["source_url"],
                "fetched_at": data["fetched_at"],
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/health")
def health():
    db_ok = True
    latest_timestamp = None
    snapshot_count = 0
    error = None
    try:
        with _connect_db() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count, MAX(reading_timestamp) AS latest_timestamp
                FROM grid_snapshots
                """
            ).fetchone()
            snapshot_count = row["count"]
            latest_timestamp = row["latest_timestamp"]
    except Exception as exc:
        db_ok = False
        error = str(exc)

    status = {
        "ok": db_ok,
        "database": {
            "ok": db_ok,
            "path": DB_PATH,
            "snapshot_count": snapshot_count,
            "latest_timestamp": latest_timestamp,
        },
        "capture": {
            "enabled": HISTORY_CAPTURE_ENABLED,
            "started": _capture_started,
            "interval_seconds": HISTORY_CAPTURE_INTERVAL_SECONDS,
        },
        "source": {
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "retries": SCRAPER_RETRIES,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
        },
        "generated_at": _now_iso(),
    }
    if error:
        status["error"] = error
    return jsonify(status), 200 if db_ok else 503


init_db()
if _should_start_capture_thread():
    start_history_capture()
atexit.register(_capture_stop.set)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
