"""
modules/analytics.py — NumPy statistical engine & anomaly detection.

All heavy number-crunching lives here: descriptive stats, Z-score
anomaly detection, node reliability rankings, and failure frequency
analysis using pure NumPy for maximum performance.
"""

import numpy as np
import pandas as pd
from modules.ingestor import load_network_uptime, load_maintenance_logs, load_assets


# ──────────────────────────────────────────────────────────────────────────────
# Uptime Statistics
# ──────────────────────────────────────────────────────────────────────────────

def uptime_stats() -> dict:
    """Compute descriptive statistics for all uptime records."""
    df = load_network_uptime()
    uptime = df["uptime_hours"].values.astype(np.float64)

    percentiles = np.percentile(uptime, [25, 50, 75])

    return {
        "mean_uptime":      round(float(np.mean(uptime)), 2),
        "median_uptime":    round(float(np.median(uptime)), 2),
        "min_uptime":       round(float(np.min(uptime)), 2),
        "max_uptime":       round(float(np.max(uptime)), 2),
        "std_deviation":    round(float(np.std(uptime)), 2),
        "variance":         round(float(np.var(uptime)), 4),
        "p25_uptime":       round(float(percentiles[0]), 2),
        "p75_uptime":       round(float(percentiles[2]), 2),
        "total_records":    int(len(uptime)),
        "overall_uptime_pct": round(float(np.mean(uptime) / 24 * 100), 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Anomaly Detection (Z-Score & Threshold)
# ──────────────────────────────────────────────────────────────────────────────

def detect_anomalies(z_threshold: float = 2.0) -> list[dict]:
    """
    Flag nodes whose uptime is more than `z_threshold` standard deviations
    below the mean.  Returns a list of anomaly dicts sorted by uptime ascending.
    """
    df = load_network_uptime()
    uptime = df["uptime_hours"].values.astype(np.float64)

    mean = np.mean(uptime)
    std  = np.std(uptime)

    if std == 0:
        return []

    z_scores = (uptime - mean) / std
    df = df.copy()
    df["z_score"] = z_scores.round(3)
    df["severity"] = pd.cut(
        df["z_score"],
        bins=[-np.inf, -3.0, -2.0, -1.0, np.inf],
        labels=["critical", "high", "medium", "normal"],
    )

    anomalies = df[df["z_score"] < -z_threshold].copy()
    anomalies = anomalies.sort_values("uptime_hours")

    result = anomalies[
        ["node_id", "node_name", "date", "uptime_hours", "downtime_hours", "z_score", "severity"]
    ].copy()
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    result["severity"] = result["severity"].astype(str)

    return result.to_dict(orient="records")


# ──────────────────────────────────────────────────────────────────────────────
# Node Reliability Rankings
# ──────────────────────────────────────────────────────────────────────────────

def node_reliability() -> list[dict]:
    """
    Rank each unique node by its mean uptime across all dates.
    Uses NumPy group-aggregation for speed.
    """
    df = load_network_uptime()
    grouped = (
        df.groupby(["node_id", "node_name"])["uptime_hours"]
        .agg(["mean", "min", "max", "std", "count"])
        .reset_index()
    )
    grouped.columns = ["node_id", "node_name", "mean_uptime", "min_uptime", "max_uptime", "std_uptime", "days_recorded"]
    grouped["mean_uptime"]   = grouped["mean_uptime"].round(2)
    grouped["min_uptime"]    = grouped["min_uptime"].round(2)
    grouped["max_uptime"]    = grouped["max_uptime"].round(2)
    grouped["std_uptime"]    = grouped["std_uptime"].fillna(0).round(3)
    grouped["uptime_pct"]    = (grouped["mean_uptime"] / 24 * 100).round(2)
    grouped["reliability"]   = pd.cut(
        grouped["uptime_pct"],
        bins=[0, 85, 95, 99, 100.1],
        labels=["poor", "fair", "good", "excellent"],
        right=False,
    ).astype(str)
    grouped = grouped.sort_values("mean_uptime", ascending=False)
    return grouped.to_dict(orient="records")


# ──────────────────────────────────────────────────────────────────────────────
# Failure Frequency
# ──────────────────────────────────────────────────────────────────────────────

def failure_frequency() -> list[dict]:
    """Count maintenance incidents per asset, enriched with asset name."""
    logs = load_maintenance_logs()
    assets = load_assets()[["asset_id", "name", "type", "location"]]

    freq = (
        logs.groupby("asset_id")
        .agg(
            failure_count=("log_id", "count"),
            unresolved=("resolved", lambda x: int((x == False).sum())),
            last_incident=("date", "max"),
        )
        .reset_index()
    )
    freq["last_incident"] = freq["last_incident"].dt.strftime("%Y-%m-%d")
    freq = freq.merge(assets, on="asset_id", how="left")
    freq = freq.sort_values("failure_count", ascending=False)
    # Replace NaN with None so FastAPI serialises cleanly as null (not NaN)
    freq = freq.where(freq.notna(), other=None)
    return freq.to_dict(orient="records")


# ──────────────────────────────────────────────────────────────────────────────
# Asset Age Distribution (NumPy histogram)
# ──────────────────────────────────────────────────────────────────────────────

def asset_age_distribution(bins: int = 5) -> dict:
    """
    Use NumPy to compute a histogram of asset ages (years).
    Returns bin edges and counts suitable for charting.
    """
    df = load_assets()
    age_years = (df["age_days"] / 365.25).values.astype(np.float64)

    counts, bin_edges = np.histogram(age_years, bins=bins)

    labels = [
        f"{bin_edges[i]:.1f}–{bin_edges[i+1]:.1f} yrs"
        for i in range(len(bin_edges) - 1)
    ]

    return {
        "labels": labels,
        "counts": counts.tolist(),
        "mean_age_years": round(float(np.mean(age_years)), 2),
        "oldest_years":   round(float(np.max(age_years)), 2),
        "newest_years":   round(float(np.min(age_years)), 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Daily Trend (per-day mean uptime across all nodes)
# ──────────────────────────────────────────────────────────────────────────────

def daily_uptime_trend() -> list[dict]:
    """Return daily mean uptime across all nodes, sorted by date."""
    df = load_network_uptime()
    trend = (
        df.groupby("date")["uptime_hours"]
        .mean()
        .reset_index()
        .sort_values("date")
    )
    trend["date"] = trend["date"].dt.strftime("%Y-%m-%d")
    trend["mean_uptime"] = trend["uptime_hours"].round(2)
    return trend[["date", "mean_uptime"]].to_dict(orient="records")
