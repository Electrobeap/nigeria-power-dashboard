"""Read-only evidence audit; never calculates or publishes research findings.

Public API samples cannot certify full database coverage. Database mode requires
an operator-provided read-only RESEARCH_DATABASE_URL, not Flask startup.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time


def timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def audit_readings(rows, *, expected_interval_seconds, now=None, since=None):
    if expected_interval_seconds <= 0:
        raise ValueError("Expected interval must be positive")
    now = now or datetime.now(timezone.utc)
    counts = Counter()
    first = last = previous = None
    maximum_gap = 0.0
    for row in rows:
        counts["rows"] += 1
        observed = timestamp(row.get("timestamp"))
        captured = timestamp(row.get("captured_at"))
        value = row.get("total_generation_mw")
        try:
            valid_value = not isinstance(value, bool) and value is not None and math.isfinite(float(value))
        except (TypeError, ValueError):
            valid_value = False
        if not valid_value:
            counts["missing_or_nonfinite_generation"] += 1
        elif float(value) < 0:
            counts["negative_generation"] += 1
        elif float(value) == 0:
            counts["zero_generation_review_required"] += 1
        if observed is None:
            counts["invalid_or_timezone_missing_timestamp"] += 1
            continue
        if observed > now:
            counts["future_readings"] += 1
        if since is not None and observed < since:
            counts["outside_requested_window"] += 1
        if captured is None:
            counts["invalid_capture_timestamp"] += 1
        elif captured < observed:
            counts["capture_before_reading"] += 1
        if previous is not None:
            gap = (observed - previous).total_seconds()
            if gap == 0:
                counts["adjacent_duplicate_timestamps"] += 1
            elif gap < 0:
                counts["nonchronological_pairs"] += 1
            elif gap > expected_interval_seconds * 1.5:
                counts["gaps_over_1_5_expected_intervals"] += 1
            maximum_gap = max(maximum_gap, gap)
        first = observed if first is None else min(first, observed)
        last = observed if last is None else max(last, observed)
        previous = observed
    return {
        "counts": dict(counts), "earliest_reading": first.isoformat() if first else None,
        "latest_reading": last.isoformat() if last else None,
        "expected_interval_seconds": expected_interval_seconds,
        "maximum_observed_gap_seconds": maximum_gap,
        "interpretation": "Collection coverage and quality only. Gaps and zero values are not confirmed outages; expected cadence is an audit assumption.",
    }


def get_public_json(url):
    import requests

    started = time.monotonic()
    with requests.get(url, headers={"User-Agent": "NigeriaPowerData-ResearchAudit/1.0",
                                   "Accept": "application/json"},
                      timeout=(5, 15), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError("Expected JSON response")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 4_000_000 or time.monotonic() - started > 30:
                raise ValueError("Audit response exceeded bounds")
            chunks.append(chunk)
        raw = b"".join(chunks)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data, hashlib.sha256(raw).hexdigest()


def public_audit():
    base = "https://nigeriapowerdata.com"
    now = datetime.now(timezone.utc)
    report = {
        "audit_time_utc": now.isoformat(), "mode": "bounded_public_sample",
        "base_url": base, "code_revision": os.environ.get("GITHUB_SHA"),
        "data_reuse_rights": "unverified", "research_calculations_performed": False,
        "full_database_coverage_verified": False,
        "limitations": [
            "The public API is limited to 2000 recent readings and may fall back outside the requested window.",
            "No historical company rows, raw source payloads, frequency telemetry, or reuse permission are established by this sample.",
            "Use a frozen operator-approved read-only export before any paper findings.",
        ],
    }
    cadence = 1800
    try:
        health, digest = get_public_json(base + "/api/health")
        capture = health.get("capture") or {}
        candidate = capture.get("interval_seconds")
        if isinstance(candidate, (int, float)) and math.isfinite(candidate) and candidate > 0:
            cadence = candidate
        database = health.get("database") or {}
        report["health"] = {
            "ok": health.get("ok"), "snapshot_count": database.get("snapshot_count"),
            "latest_timestamp": database.get("latest_timestamp"),
            "response_sha256": digest,
        }
    except Exception as exc:
        report["health"] = {"available": False, "error_type": type(exc).__name__}
    try:
        payload, digest = get_public_json(base + "/api/history?hours=720&limit=2000")
        rows = payload.get("history")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("Unexpected history schema")
        report["history"] = audit_readings(rows, expected_interval_seconds=cadence,
                                           now=now, since=now - timedelta(hours=720))
        report["history"]["response_sha256"] = digest
        report["history"]["sample_limit_reached"] = len(rows) >= 2000
        report["history"]["available"] = True
    except Exception as exc:
        report["history"] = {"available": False, "error_type": type(exc).__name__}
    return report


def database_audit(*, expected_interval_seconds):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    uri = os.environ.get("RESEARCH_DATABASE_URL")
    if not uri:
        raise ValueError("Set RESEARCH_DATABASE_URL to an operator-approved read-only database")
    url = make_url(uri)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if not url.drivername.startswith(("postgresql", "sqlite")):
        raise ValueError("Only PostgreSQL or SQLite is supported")
    if url.drivername.startswith("sqlite") and (not url.database or not Path(url.database).is_file()):
        raise ValueError("SQLite audit requires an existing database file")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            with connection.begin():
                if engine.dialect.name == "postgresql":
                    connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                    connection.execute(text("SET LOCAL statement_timeout = '30000'"))
                else:
                    connection.execute(text("PRAGMA query_only = ON"))

                # Project scalar columns; never load ORM relationships or large raw JSON.
                rows = connection.execute(text(
                    "SELECT reading_timestamp AS timestamp, captured_at, total_generation_mw "
                    "FROM grid_snapshots ORDER BY reading_timestamp"
                ).execution_options(stream_results=True, yield_per=1000)).mappings()

                def normalized_rows():
                    for row in rows:
                        result = dict(row)
                        # SQLite's storage convention in this repository is naive UTC.
                        if engine.dialect.name == "sqlite":
                            for key in ("timestamp", "captured_at"):
                                value = result[key]
                                parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
                                if parsed is not None and parsed.tzinfo is None:
                                    result[key] = parsed.replace(tzinfo=timezone.utc)
                        yield result

                report = audit_readings(normalized_rows(), expected_interval_seconds=expected_interval_seconds)
                report["source_groups"] = [dict(row) for row in connection.execute(text(
                    "SELECT source, source_url, COUNT(*) AS rows FROM grid_snapshots GROUP BY source, source_url"
                )).mappings()]
                report["entity_tables"] = {}
                for table, name, value in (
                    ("genco_data", "plant", "generation_mw"),
                    ("disco_data", "company", "load_allocation_mw"),
                ):
                    # Identifiers come only from the fixed tuple above.
                    report["entity_tables"][table] = [dict(row) for row in connection.execute(text(
                        f"SELECT {name} AS entity, COUNT(*) AS rows, COUNT(DISTINCT snapshot_id) AS snapshots, "
                        f"SUM(CASE WHEN {value} IS NULL THEN 1 ELSE 0 END) AS missing_values "
                        f"FROM {table} GROUP BY {name} ORDER BY {name}"
                    )).mappings()]
                report.update({
                    "mode": "read_only_database_quality_audit", "audit_time_utc": datetime.now(timezone.utc).isoformat(),
                    "data_reuse_rights": "unverified", "research_calculations_performed": False,
                    "timestamp_basis": "Stored timestamps; source-versus-fetch fallback still requires raw-payload validation.",
                    "limitations": ["Full row coverage does not establish source completeness or a licence to redistribute data."],
                })
                return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("public", "database"))
    parser.add_argument("--expected-interval-seconds", type=int, default=1800)
    args = parser.parse_args()
    try:
        report = public_audit() if args.mode == "public" else database_audit(
            expected_interval_seconds=args.expected_interval_seconds)
    except Exception as exc:
        # Database exceptions may contain credentials or SQL parameters.
        print(json.dumps({"audit_failed": True, "error_type": type(exc).__name__}))
        raise SystemExit(1)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
