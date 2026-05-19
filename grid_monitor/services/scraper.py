import copy
import logging
import re
import threading
import time
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup
from flask import current_app

from grid_monitor.utils.logging import log_event
from grid_monitor.utils.time import utc_now_iso


class SourceUnavailable(RuntimeError):
    pass


_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _clean_number(value: str) -> float:
    return float(value.replace(",", "").strip())


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def _cached(key: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    current_ts = time.time()
    ttl = current_app.config["GRID_CACHE_TTL_SECONDS"]
    with _cache_lock:
        cached = _cache.get(key)
        if cached and current_ts - cached["loaded_at"] < ttl:
            return _copy_payload(cached["value"])

    try:
        value = loader()
    except Exception as exc:
        with _cache_lock:
            cached = _cache.get(key)
        if cached:
            stale = _copy_payload(cached["value"])
            stale["stale"] = True
            stale["stale_age_seconds"] = round(current_ts - cached["loaded_at"])
            stale["source_error"] = str(exc)
            log_event(
                "cache_stale_fallback",
                logging.WARNING,
                cache_key=key,
                stale_age_seconds=stale["stale_age_seconds"],
                error=str(exc),
            )
            return stale
        raise

    with _cache_lock:
        _cache[key] = {"loaded_at": current_ts, "value": value}
    return _copy_payload(value)


def _fetch_text(url: str) -> str:
    headers = {
        "User-Agent": (
            "NigeriaPowerDashboard/2.0 "
            "(public grid statistics scraper; contact site owner if blocked)"
        )
    }
    timeout = current_app.config["GRID_SOURCE_TIMEOUT_SECONDS"]
    retries = current_app.config["GRID_SCRAPER_RETRIES"]
    backoff = current_app.config["GRID_SCRAPER_BACKOFF_SECONDS"]
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            started = time.perf_counter()
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            log_event(
                "source_fetch_ok",
                url=url,
                attempt=attempt,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
            )
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            log_event(
                "source_fetch_failed",
                logging.WARNING,
                url=url,
                attempt=attempt,
                max_attempts=retries,
                error=str(exc),
            )
            if attempt < retries:
                time.sleep(backoff * attempt)

    raise SourceUnavailable(f"Could not fetch NIGGRID source after retries: {last_error}")


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
    source_url = current_app.config["NIGGRID_DASHBOARD_URL"]
    html = _fetch_text(source_url)
    text = _page_text(html)
    realtime = _extract_realtime(text)
    return {
        **realtime,
        "daily": _extract_daily_performance(text),
        "gencos": _extract_gencos(text),
        "source": "NISO NIGGRID 24hr Grid Performance Dashboard",
        "source_url": source_url,
        "fetched_at": utc_now_iso(),
    }


def _load_disco_profile() -> dict[str, Any]:
    source_url = current_app.config["NIGGRID_DISCO_URL"]
    html = _fetch_text(source_url)
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
        "source_url": source_url,
        "fetched_at": utc_now_iso(),
    }


def get_dashboard_payload() -> dict[str, Any]:
    return _cached("dashboard", _load_dashboard)


def get_disco_profile() -> dict[str, Any]:
    return _cached("disco_profile", _load_disco_profile)


def get_live_grid_payload() -> dict[str, Any]:
    dashboard = get_dashboard_payload()
    try:
        disco_profile = get_disco_profile()
    except Exception as exc:
        log_event("disco_profile_fallback_empty", logging.WARNING, error=str(exc))
        disco_profile = {
            "as_at": None,
            "discos": [],
            "total_load_allocation_mw": None,
            "source": "NISO NIGGRID DISCOs Load Profile",
            "source_url": current_app.config["NIGGRID_DISCO_URL"],
            "fetched_at": utc_now_iso(),
            "error": str(exc),
        }
    return {**dashboard, "disco_profile": disco_profile}
