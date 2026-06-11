"""
modules/ingestor.py — Pandas data loading & cleaning pipeline.

UPGRADE: TTLCache added — DataFrames are cached for 60 seconds to avoid
re-reading CSVs on every API request. Call invalidate_cache() after an
upload to force a fresh read on the next request.
"""

import pandas as pd
from pathlib import Path
from cachetools import TTLCache, cached
from threading import Lock

DATA_DIR = Path(__file__).parent.parent / "data"

# ── Cache store: max 10 DataFrames, each lives for 60 seconds ────────────────
_cache: TTLCache = TTLCache(maxsize=10, ttl=60)
_lock = Lock()


def invalidate_cache() -> None:
    """Clear all cached DataFrames (call after a file upload)."""
    with _lock:
        _cache.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Loaders  (cached)
# ──────────────────────────────────────────────────────────────────────────────

@cached(cache=_cache, key=lambda: "assets", lock=_lock)
def load_assets() -> pd.DataFrame:
    """Load and clean the hardware asset inventory (cached 60 s)."""
    df = pd.read_csv(DATA_DIR / "assets.csv")
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["purchase_date"] = pd.to_datetime(df["purchase_date"], errors="coerce")
    df["status"] = df["status"].str.strip().str.title()
    df.dropna(subset=["asset_id", "name", "purchase_date"], inplace=True)
    df["age_days"] = (pd.Timestamp.now() - df["purchase_date"]).dt.days
    return df


@cached(cache=_cache, key=lambda: "uptime", lock=_lock)
def load_network_uptime() -> pd.DataFrame:
    """Load and clean network node uptime records (cached 60 s)."""
    df = pd.read_csv(DATA_DIR / "network_uptime.csv")
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["uptime_hours"] = pd.to_numeric(df["uptime_hours"], errors="coerce")
    df["downtime_hours"] = pd.to_numeric(df["downtime_hours"], errors="coerce")
    df.dropna(subset=["node_id", "date", "uptime_hours"], inplace=True)
    df["uptime_pct"] = (df["uptime_hours"] / 24 * 100).round(2)
    return df


@cached(cache=_cache, key=lambda: "maintenance", lock=_lock)
def load_maintenance_logs() -> pd.DataFrame:
    """Load and clean the maintenance / issue log (cached 60 s)."""
    df = pd.read_csv(DATA_DIR / "maintenance_logs.csv")
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["resolved"] = df["resolved"].astype(str).str.strip().str.title()
    df["resolved"] = df["resolved"].map({"True": True, "False": False})
    df.dropna(subset=["log_id", "asset_id"], inplace=True)
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Schema validation helpers
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {
    "assets":      {"asset_id", "name", "type", "location", "status", "purchase_date"},
    "uptime":      {"node_id", "node_name", "date", "uptime_hours", "downtime_hours"},
    "maintenance": {"log_id", "asset_id", "issue", "resolved", "date"},
}


def validate_columns(df: pd.DataFrame, dataset: str) -> list[str]:
    """Return list of missing required columns for a given dataset key."""
    normalised = set(df.columns.str.strip().str.lower().str.replace(" ", "_"))
    required = REQUIRED_COLUMNS.get(dataset, set())
    return sorted(required - normalised)
