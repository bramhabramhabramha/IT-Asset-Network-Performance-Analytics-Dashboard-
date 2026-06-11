"""
modules/reports.py — Automated summary report generator.

Aggregates all analytics into a single structured report dictionary
that can be serialised to JSON, stored in SQLite, or returned via API.
"""

from datetime import datetime, timezone
import numpy as np

from modules.ingestor import load_assets, load_maintenance_logs, load_network_uptime
from modules.analytics import (
    uptime_stats,
    detect_anomalies,
    failure_frequency,
    node_reliability,
    asset_age_distribution,
    daily_uptime_trend,
)


def generate_summary_report() -> dict:
    """
    Build a comprehensive analytics summary report.

    Returns a single dict with:
      - report metadata
      - asset overview
      - network health KPIs
      - maintenance health
      - top anomalies
      - top failing assets
    """
    # ── Raw data ──────────────────────────────────────────────────────────────
    assets   = load_assets()
    logs     = load_maintenance_logs()
    uptime   = load_network_uptime()
    stats    = uptime_stats()
    failures = failure_frequency()
    anomalies = detect_anomalies()
    reliability = node_reliability()

    # ── Asset Overview ────────────────────────────────────────────────────────
    status_counts   = assets["status"].value_counts().to_dict()
    type_counts     = assets["type"].value_counts().to_dict()
    location_counts = assets["location"].value_counts().to_dict()

    age_dist = asset_age_distribution()

    # ── Network Health ────────────────────────────────────────────────────────
    excellent_nodes = [r for r in reliability if r["reliability"] == "excellent"]
    poor_nodes      = [r for r in reliability if r["reliability"] == "poor"]

    # ── Maintenance Health ────────────────────────────────────────────────────
    total_incidents  = int(len(logs))
    open_incidents   = int((logs["resolved"] == False).sum())
    resolved_rate    = round((1 - open_incidents / max(total_incidents, 1)) * 100, 1)
    incident_types   = logs["issue"].str.split(" - ").str[0].value_counts().head(5).to_dict()

    # ── Build Report ──────────────────────────────────────────────────────────
    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_version": "1.0",
            "data_sources": ["assets.csv", "network_uptime.csv", "maintenance_logs.csv"],
        },
        "asset_overview": {
            "total_assets":      int(len(assets)),
            "by_status":         status_counts,
            "by_type":           type_counts,
            "by_location":       location_counts,
            "age_distribution":  age_dist,
            "oldest_asset_days": int(assets["age_days"].max()),
            "newest_asset_days": int(assets["age_days"].min()),
        },
        "network_health": {
            **stats,
            "total_nodes":           int(uptime["node_id"].nunique()),
            "excellent_reliability": len(excellent_nodes),
            "poor_reliability":      len(poor_nodes),
            "anomalies_detected":    len(anomalies),
            "daily_trend":           daily_uptime_trend(),
            "top_performers":        excellent_nodes[:5],
            "worst_performers":      poor_nodes[:5],
        },
        "maintenance_health": {
            "total_incidents":   total_incidents,
            "open_incidents":    open_incidents,
            "resolved_incidents": total_incidents - open_incidents,
            "resolution_rate_pct": resolved_rate,
            "top_issue_categories": incident_types,
        },
        "top_anomalies":      anomalies[:10],
        "top_failing_assets": failures[:5],
    }

    return report
