import os
import re
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template


app = Flask(__name__)

NIGGRID_DASHBOARD_URL = "https://www.niggrid.org/Dashboard"
NIGGRID_DISCO_URL = "https://www.niggrid.org/DisCoLoadProfile"
REQUEST_TIMEOUT_SECONDS = 12
CACHE_TTL_SECONDS = 60

_cache: dict[str, dict[str, Any]] = {}


class SourceUnavailable(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cached(key: str, loader):
    current_ts = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(key)
    if cached and current_ts - cached["loaded_at"] < CACHE_TTL_SECONDS:
        return cached["value"]

    value = loader()
    _cache[key] = {"loaded_at": current_ts, "value": value}
    return value


def _fetch_text(url: str) -> str:
    headers = {
        "User-Agent": (
            "NigeriaPowerDashboard/1.0 "
            "(public grid statistics scraper; contact site owner if blocked)"
        )
    }
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


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


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/data")
def legacy_data():
    try:
        data = _grid_payload()
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
    except Exception as exc:
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/grid/live")
def live_grid():
    try:
        return jsonify(_grid_payload())
    except Exception as exc:
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


@app.get("/api/grid/gencos")
def gencos():
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


@app.get("/api/grid/discos")
def discos():
    try:
        return jsonify(_cached("disco_profile", _load_disco_profile))
    except Exception as exc:
        return jsonify({"error": str(exc), "source": "NISO NIGGRID"}), 503


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
