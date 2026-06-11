"""
tests/test_api.py — pytest integration test suite.

Covers every endpoint group using FastAPI's built-in TestClient (httpx).
Run with:
    pytest tests/ -v
"""

import io
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app

DATA_DIR = Path("data")
client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure the TTL cache is cleared between tests for clean state."""
    from modules.ingestor import invalidate_cache
    invalidate_cache()
    yield
    invalidate_cache()


# ─────────────────────────────────────────────────────────────────────────────
# System
# ─────────────────────────────────────────────────────────────────────────────

class TestSystem:
    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "ws_clients" in body

    def test_dashboard_serves_html(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


# ─────────────────────────────────────────────────────────────────────────────
# Assets
# ─────────────────────────────────────────────────────────────────────────────

class TestAssets:
    def test_get_assets_default_pagination(self):
        r = client.get("/api/assets")
        assert r.status_code == 200
        body = r.json()
        # Pagination envelope keys
        assert "total" in body
        assert "page" in body
        assert "limit" in body
        assert "total_pages" in body
        assert "items" in body
        assert isinstance(body["items"], list)
        assert body["page"] == 1
        assert body["limit"] == 20

    def test_get_assets_filter_active(self):
        r = client.get("/api/assets?status=Active")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(a["status"] == "Active" for a in items)

    def test_get_assets_filter_inactive(self):
        r = client.get("/api/assets?status=Inactive")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(a["status"] == "Inactive" for a in items)

    def test_get_assets_pagination_page2(self):
        r1 = client.get("/api/assets?page=1&limit=5")
        r2 = client.get("/api/assets?page=2&limit=5")
        assert r1.status_code == 200
        assert r2.status_code == 200
        ids1 = [a["asset_id"] for a in r1.json()["items"]]
        ids2 = [a["asset_id"] for a in r2.json()["items"]]
        # Pages must be disjoint
        assert not set(ids1) & set(ids2)

    def test_get_asset_types(self):
        r = client.get("/api/assets/types")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert all("type" in item and "count" in item for item in body)

    def test_get_asset_locations(self):
        r = client.get("/api/assets/locations")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert all("location" in item and "count" in item for item in body)

    def test_get_asset_age_distribution(self):
        r = client.get("/api/assets/age")
        assert r.status_code == 200
        body = r.json()
        assert "labels" in body
        assert "counts" in body
        assert "mean_age_years" in body
        assert len(body["labels"]) == len(body["counts"])


# ─────────────────────────────────────────────────────────────────────────────
# Network / Uptime
# ─────────────────────────────────────────────────────────────────────────────

class TestNetwork:
    def test_uptime_stats_shape(self):
        r = client.get("/api/uptime/stats")
        assert r.status_code == 200
        body = r.json()
        required = {
            "mean_uptime", "median_uptime", "min_uptime", "max_uptime",
            "std_deviation", "variance", "p25_uptime", "p75_uptime",
            "total_records", "overall_uptime_pct",
        }
        assert required <= body.keys()

    def test_uptime_stats_values_in_range(self):
        body = client.get("/api/uptime/stats").json()
        assert 0 <= body["mean_uptime"] <= 24
        assert 0 <= body["overall_uptime_pct"] <= 100
        assert body["min_uptime"] <= body["mean_uptime"] <= body["max_uptime"]

    def test_anomalies_default_threshold(self):
        r = client.get("/api/uptime/anomalies")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert "anomalies" in body
        assert body["count"] == len(body["anomalies"])

    def test_anomalies_custom_threshold(self):
        r = client.get("/api/uptime/anomalies?z_threshold=1.5")
        assert r.status_code == 200
        # Looser threshold → at least as many anomalies as default 2.0
        loose = r.json()["count"]
        strict = client.get("/api/uptime/anomalies?z_threshold=2.5").json()["count"]
        assert loose >= strict

    def test_anomaly_severity_field(self):
        body = client.get("/api/uptime/anomalies?z_threshold=1.0").json()
        for a in body["anomalies"]:
            assert a["severity"] in {"critical", "high", "medium", "normal"}

    def test_node_reliability(self):
        r = client.get("/api/uptime/reliability")
        assert r.status_code == 200
        nodes = r.json()["nodes"]
        assert len(nodes) > 0
        for n in nodes:
            assert n["reliability"] in {"excellent", "good", "fair", "poor"}
            assert 0 <= n["uptime_pct"] <= 100

    def test_daily_trend(self):
        r = client.get("/api/uptime/trend")
        assert r.status_code == 200
        trend = r.json()["trend"]
        assert len(trend) > 0
        for point in trend:
            assert "date" in point
            assert "mean_uptime" in point
            assert 0 <= point["mean_uptime"] <= 24

    def test_uptime_history(self):
        # First trigger a snapshot save
        client.get("/api/uptime/stats")
        r = client.get("/api/uptime/history?limit=5")
        assert r.status_code == 200
        assert "snapshots" in r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Maintenance
# ─────────────────────────────────────────────────────────────────────────────

class TestMaintenance:
    def test_get_logs_default(self):
        r = client.get("/api/maintenance/logs")
        assert r.status_code == 200
        body = r.json()
        assert "total" in body and "items" in body

    def test_get_logs_filter_resolved(self):
        r = client.get("/api/maintenance/logs?resolved=true")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(item["resolved"] is True for item in items)

    def test_get_logs_filter_open(self):
        r = client.get("/api/maintenance/logs?resolved=false")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(item["resolved"] is False for item in items)

    def test_get_logs_pagination(self):
        r = client.get("/api/maintenance/logs?page=1&limit=3")
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 3

    def test_failure_frequency(self):
        r = client.get("/api/maintenance/failures")
        assert r.status_code == 200
        body = r.json()
        assert "failure_frequency" in body
        freq = body["failure_frequency"]
        assert len(freq) > 0
        # Should be sorted descending
        counts = [f["failure_count"] for f in freq]
        assert counts == sorted(counts, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────

class TestReports:
    def test_summary_report_structure(self):
        r = client.get("/api/report/summary")
        assert r.status_code == 200
        body = r.json()
        assert "metadata" in body
        assert "asset_overview" in body
        assert "network_health" in body
        assert "maintenance_health" in body
        assert "top_anomalies" in body
        assert "top_failing_assets" in body

    def test_summary_asset_count_positive(self):
        body = client.get("/api/report/summary").json()
        assert body["asset_overview"]["total_assets"] > 0

    def test_summary_resolution_rate_valid(self):
        body = client.get("/api/report/summary").json()
        rate = body["maintenance_health"]["resolution_rate_pct"]
        assert 0.0 <= rate <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# File Upload
# ─────────────────────────────────────────────────────────────────────────────

VALID_ASSETS_CSV = (
    "asset_id,name,type,location,status,purchase_date\n"
    "T001,Test Device,Laptop,Floor-1,Active,2022-01-01\n"
)

INVALID_CSV_MISSING_COL = (
    "asset_id,name\n"
    "T001,Test Device\n"
)


class TestUpload:

    @pytest.fixture(autouse=True)
    def _backup_restore_assets(self):
        """Back up assets.csv before each upload test and restore it after."""
        original = DATA_DIR / "assets.csv"
        backup   = DATA_DIR / "assets.csv.bak"
        shutil.copy2(original, backup)
        yield
        shutil.copy2(backup, original)
        backup.unlink(missing_ok=True)
        # Bust cache so subsequent tests see the restored file
        from modules.ingestor import invalidate_cache
        invalidate_cache()

    def test_upload_valid_assets(self):
        f = io.BytesIO(VALID_ASSETS_CSV.encode())
        r = client.post(
            "/api/upload/assets",
            files={"file": ("assets.csv", f, "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["rows"] == 1
        assert "asset_id" in body["columns"]

    def test_upload_wrong_extension(self):
        f = io.BytesIO(b"col1,col2\n1,2")
        r = client.post(
            "/api/upload/assets",
            files={"file": ("data.xlsx", f, "application/vnd.ms-excel")},
        )
        assert r.status_code == 400
        assert "csv" in r.json()["detail"].lower()

    def test_upload_missing_required_columns(self):
        f = io.BytesIO(INVALID_CSV_MISSING_COL.encode())
        r = client.post(
            "/api/upload/assets",
            files={"file": ("assets.csv", f, "text/csv")},
        )
        assert r.status_code == 422
        assert "Missing required columns" in r.json()["detail"]

    def test_upload_cache_invalidated_after_upload(self):
        """After a successful upload the cache should be cleared."""
        # Prime the cache
        client.get("/api/assets")
        # Upload single-row file
        f = io.BytesIO(VALID_ASSETS_CSV.encode())
        client.post(
            "/api/upload/assets",
            files={"file": ("assets.csv", f, "text/csv")},
        )
        # Fetch again — should reflect the uploaded single-row dataset
        r = client.get("/api/assets?limit=100")
        assert r.status_code == 200
        assert r.json()["total"] == 1

