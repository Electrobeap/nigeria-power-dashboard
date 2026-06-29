import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GRID_DATA_DIR", BASE_DIR / "data"))
POSTGRES_DRIVER = os.environ.get("POSTGRES_DRIVER", "psycopg").strip().lower()
if POSTGRES_DRIVER != "psycopg":
    POSTGRES_DRIVER = "psycopg"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _normalize_database_uri(uri: str | None) -> str:
    if uri:
        uri = uri.strip()
        if uri.startswith("postgres://"):
            return uri.replace("postgres://", f"postgresql+{POSTGRES_DRIVER}://", 1)
        if uri.startswith("postgresql://") and "+" not in uri.split("://", 1)[0]:
            return uri.replace("postgresql://", f"postgresql+{POSTGRES_DRIVER}://", 1)
        return uri

    sqlite_path = os.environ.get("GRID_SQLITE_PATH") or str(DATA_DIR / "grid_history.sqlite3")
    return f"sqlite:///{Path(sqlite_path).resolve().as_posix()}"


def _safe_database_uri(uri: str) -> str:
    if "@" not in uri or "://" not in uri:
        return uri
    scheme, rest = uri.split("://", 1)
    return f"{scheme}://***:***@{rest.split('@', 1)[1]}"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("GRID_DATABASE_URL")
    )
    SAFE_DATABASE_URI = _safe_database_uri(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    POSTGRES_DRIVER = POSTGRES_DRIVER
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": _env_int("DB_POOL_RECYCLE_SECONDS", 280),
    }
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite:///"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"check_same_thread": False}

    NIGGRID_DASHBOARD_URL = os.environ.get(
        "NIGGRID_DASHBOARD_URL", "https://www.niggrid.org/Dashboard"
    )
    NIGGRID_DISCO_URL = os.environ.get(
        "NIGGRID_DISCO_URL", "https://www.niggrid.org/DisCoLoadProfile"
    )

    GRID_SOURCE_TIMEOUT_SECONDS = _env_float("GRID_SOURCE_TIMEOUT_SECONDS", 12.0)
    GRID_SCRAPER_RETRIES = max(1, _env_int("GRID_SCRAPER_RETRIES", 2))
    GRID_SCRAPER_BACKOFF_SECONDS = _env_float("GRID_SCRAPER_BACKOFF_SECONDS", 1.5)
    GRID_CACHE_TTL_SECONDS = _env_int("GRID_CACHE_TTL_SECONDS", 60)

    WEB_SCHEDULER_ENABLED = _env_bool("WEB_SCHEDULER_ENABLED", False)
    HISTORY_CAPTURE_ENABLED = _env_bool("HISTORY_CAPTURE_ENABLED", True)
    HISTORY_CAPTURE_INTERVAL_SECONDS = max(
        60, _env_int("HISTORY_CAPTURE_INTERVAL_SECONDS", 1800)
    )
    HISTORY_CAPTURE_ON_STARTUP = _env_bool("HISTORY_CAPTURE_ON_STARTUP", True)
    ROLLING_AVERAGE_WINDOW = max(1, _env_int("ROLLING_AVERAGE_WINDOW", 12))
    ANALYTICS_CACHE_TTL_SECONDS = _env_int("ANALYTICS_CACHE_TTL_SECONDS", 120)
    OUTAGE_DROP_THRESHOLD_PERCENT = _env_float("OUTAGE_DROP_THRESHOLD_PERCENT", 35.0)
    OUTAGE_CRITICAL_MW = _env_float("OUTAGE_CRITICAL_MW", 2500.0)
    RUN_MIGRATIONS_ON_STARTUP = _env_bool("RUN_MIGRATIONS_ON_STARTUP", True)
    REQUIRE_DATABASE_ON_STARTUP = _env_bool("REQUIRE_DATABASE_ON_STARTUP", False)
    AUTO_CREATE_TABLES = _env_bool("AUTO_CREATE_TABLES", True)
    DISTRIBUTION_POWER_FACTOR = _env_float("DISTRIBUTION_POWER_FACTOR", 0.9)
    TRANSFORMER_BASE_UTILIZATION = _env_float("TRANSFORMER_BASE_UTILIZATION", 0.82)
    TRANSFORMER_WARNING_UTILIZATION_PERCENT = _env_float(
        "TRANSFORMER_WARNING_UTILIZATION_PERCENT", 85.0
    )
    TRANSFORMER_OVERLOAD_UTILIZATION_PERCENT = _env_float(
        "TRANSFORMER_OVERLOAD_UTILIZATION_PERCENT", 95.0
    )
    SETTLEMENT_GROWTH_BASE_PERCENT = _env_float("SETTLEMENT_GROWTH_BASE_PERCENT", 3.8)

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    API_NAME = "Nigeria Power Grid Monitor API"
    API_VERSION = os.environ.get("API_VERSION", "2.0.0")
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://nigeriapowerdata.com").rstrip("/")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hello@nigeriapowerdata.com")
    RESEARCH_EMAIL = os.environ.get("RESEARCH_EMAIL", CONTACT_EMAIL)
    ADS_EMAIL = os.environ.get("ADS_EMAIL", CONTACT_EMAIL)
    GEOGRAPHY_DATASET_PATH = os.environ.get("GEOGRAPHY_DATASET_PATH")

    GRID_STRESS_CRITICAL_MW = _env_float("GRID_STRESS_CRITICAL_MW", 3000.0)
    GRID_STRESS_STRESSED_MW = _env_float("GRID_STRESS_STRESSED_MW", 4500.0)
    GRID_STRESS_STABLE_MW = _env_float("GRID_STRESS_STABLE_MW", 5500.0)
