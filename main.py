"""
main.py — FastAPI application entry point.

UPGRADES ADDED:
  ✅ CORS middleware (cross-origin frontend support)
  ✅ TTLCache (via ingestor) — no redundant CSV reads
  ✅ Pagination — ?page=&limit= on /api/assets and /api/maintenance/logs
  ✅ File Upload — POST /api/upload/{dataset} with schema validation
  ✅ WebSocket — /ws/live streams uptime stats every 5 s
"""

import asyncio
import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from db.database import (
    init_db,
    save_uptime_snapshot,
    get_uptime_history,
    save_anomalies,
    save_failures,
)
from modules.analytics import (
    uptime_stats,
    detect_anomalies,
    failure_frequency,
    node_reliability,
    asset_age_distribution,
    daily_uptime_trend,
)
from modules.ingestor import (
    load_assets,
    load_maintenance_logs,
    load_network_uptime,
    invalidate_cache,
    validate_columns,
    DATA_DIR,
)
from modules.reports import generate_summary_report


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket connection manager
# ──────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """Tracks all active WebSocket clients and broadcasts messages to them."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.remove(ws)

    async def broadcast(self, data: dict) -> None:
        payload = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


# ──────────────────────────────────────────────────────────────────────────────
# Background broadcaster task
# ──────────────────────────────────────────────────────────────────────────────

async def _live_broadcaster() -> None:
    """Push uptime stats to all WebSocket clients every 5 seconds."""
    while True:
        if manager.active:
            try:
                stats = uptime_stats()
                anomalies = detect_anomalies()
                await manager.broadcast(
                    {
                        "event": "live_update",
                        "uptime_stats": stats,
                        "anomaly_count": len(anomalies),
                        "active_connections": len(manager.active),
                    }
                )
            except Exception as exc:
                await manager.broadcast({"event": "error", "detail": str(exc)})
        await asyncio.sleep(5)


# ──────────────────────────────────────────────────────────────────────────────
# App Lifecycle
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise SQLite schema and start the live broadcast loop on startup."""
    init_db()
    task = asyncio.create_task(_live_broadcaster())
    yield
    task.cancel()


app = FastAPI(
    title="IT Asset & Network Performance Analytics",
    description=(
        "REST API serving real-time IT asset tracking, NumPy-powered "
        "network performance analytics, and automated anomaly detection "
        "across enterprise infrastructure."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files & dashboard ──────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    """Serve the HTML dashboard."""
    return FileResponse(str(STATIC_DIR / "dashboard.html"))


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _paginate(records: list, page: int, limit: int) -> dict:
    """Return a pagination envelope for a flat list."""
    total = len(records)
    start = (page - 1) * limit
    end   = start + limit
    return {
        "total":       total,
        "page":        page,
        "limit":       limit,
        "total_pages": max(1, -(-total // limit)),   # ceiling division
        "items":       records[start:end],
    }


# ──────────────────────────────────────────────────────────────────────────────
# System
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Simple liveness probe."""
    return {
        "status":   "ok",
        "service":  "IT Asset Analytics API",
        "version":  "2.0.0",
        "ws_clients": len(manager.active),
    }


# ──────────────────────────────────────────────────────────────────────────────
# File Upload  ← NEW
# ──────────────────────────────────────────────────────────────────────────────

DATASET_FILES: dict[str, str] = {
    "assets":      "assets.csv",
    "uptime":      "network_uptime.csv",
    "maintenance": "maintenance_logs.csv",
}


@app.post("/api/upload/{dataset}", tags=["Upload"])
async def upload_dataset(
    dataset: Literal["assets", "uptime", "maintenance"],
    file: UploadFile = File(..., description="CSV file to ingest"),
):
    """
    Replace one of the three data sources with an uploaded CSV file.

    - **dataset**: `assets` | `uptime` | `maintenance`
    - Validates required columns before overwriting the existing file.
    - Automatically invalidates the TTL cache so the next request reads fresh data.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    import pandas as pd
    import io

    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse CSV: {exc}")

    missing = validate_columns(df, dataset)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns for '{dataset}': {missing}",
        )

    # Overwrite the data file
    dest = DATA_DIR / DATASET_FILES[dataset]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(raw)

    # Bust the TTL cache so analytics picks up new data immediately
    invalidate_cache()

    return {
        "message":  f"'{dataset}' dataset replaced successfully.",
        "filename": file.filename,
        "rows":     len(df),
        "columns":  list(df.columns),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Assets  (with pagination)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/assets", tags=["Assets"])
def get_assets(
    status: str | None = Query(None, description="Filter: Active | Inactive | Maintenance"),
    page:   int        = Query(1,    ge=1,  description="Page number"),
    limit:  int        = Query(20,   ge=1, le=100, description="Items per page"),
):
    """Return paginated hardware assets, optionally filtered by status."""
    df = load_assets()
    if status:
        df = df[df["status"].str.lower() == status.lower()]
    records = df.copy()
    records["purchase_date"] = records["purchase_date"].dt.strftime("%Y-%m-%d")
    return _paginate(records.to_dict(orient="records"), page, limit)


@app.get("/api/assets/types", tags=["Assets"])
def get_asset_types():
    """Return asset count grouped by type."""
    df     = load_assets()
    counts = df["type"].value_counts().reset_index()
    counts.columns = ["type", "count"]
    return counts.to_dict(orient="records")


@app.get("/api/assets/locations", tags=["Assets"])
def get_asset_locations():
    """Return asset count grouped by location."""
    df     = load_assets()
    counts = df["location"].value_counts().reset_index()
    counts.columns = ["location", "count"]
    return counts.to_dict(orient="records")


@app.get("/api/assets/age", tags=["Assets"])
def get_asset_age_distribution():
    """NumPy histogram of asset ages in years."""
    return asset_age_distribution()


# ──────────────────────────────────────────────────────────────────────────────
# Network Uptime
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/uptime/stats", tags=["Network"])
def get_uptime_stats():
    """Descriptive statistics for all uptime records (NumPy-powered)."""
    stats = uptime_stats()
    save_uptime_snapshot(stats)
    return stats


@app.get("/api/uptime/anomalies", tags=["Network"])
def get_anomalies(
    z_threshold: float = Query(2.0, description="Z-score threshold (default 2.0)"),
):
    """Detect nodes with critically low uptime via Z-score analysis."""
    anomalies = detect_anomalies(z_threshold=z_threshold)
    if anomalies:
        save_anomalies(anomalies)
    return {"count": len(anomalies), "anomalies": anomalies}


@app.get("/api/uptime/reliability", tags=["Network"])
def get_node_reliability():
    """Rank all nodes by mean uptime and assign reliability tier."""
    return {"nodes": node_reliability()}


@app.get("/api/uptime/trend", tags=["Network"])
def get_daily_trend():
    """Daily mean uptime across all nodes — suitable for time-series charts."""
    return {"trend": daily_uptime_trend()}


@app.get("/api/uptime/history", tags=["Network"])
def get_uptime_history_endpoint(
    limit: int = Query(20, ge=1, le=100),
):
    """Retrieve historical uptime snapshots stored in SQLite."""
    return {"snapshots": get_uptime_history(limit=limit)}


# ──────────────────────────────────────────────────────────────────────────────
# Maintenance  (with pagination)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/maintenance/logs", tags=["Maintenance"])
def get_maintenance_logs(
    resolved: bool | None = Query(None),
    page:     int         = Query(1,  ge=1),
    limit:    int         = Query(20, ge=1, le=100),
):
    """Return paginated maintenance logs, optionally filtered by resolved status."""
    df = load_maintenance_logs()
    if resolved is not None:
        df = df[df["resolved"] == resolved]
    df = df.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return _paginate(df.to_dict(orient="records"), page, limit)


@app.get("/api/maintenance/failures", tags=["Maintenance"])
def get_failures():
    """Failure frequency per asset, sorted by incident count descending."""
    failures = failure_frequency()
    save_failures(failures)
    return {"count": len(failures), "failure_frequency": failures}


# ──────────────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/report/summary", tags=["Reports"])
def get_summary_report():
    """
    Full analytics summary — asset overview, network KPIs,
    maintenance health, anomalies, and top failing assets.
    """
    return generate_summary_report()


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket — Live Feed  ← NEW
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """
    Connect to receive live uptime stats pushed every 5 seconds.

    Message format:
    ```json
    {
      "event": "live_update",
      "uptime_stats": { ... },
      "anomaly_count": 3,
      "active_connections": 1
    }
    ```
    """
    await manager.connect(ws)
    # Send an immediate snapshot on connect so the client doesn't wait 5 s
    try:
        stats     = uptime_stats()
        anomalies = detect_anomalies()
        await ws.send_text(json.dumps({
            "event":              "connected",
            "uptime_stats":       stats,
            "anomaly_count":      len(anomalies),
            "active_connections": len(manager.active),
        }))
        # Keep connection alive — broadcaster loop handles the pushing
        while True:
            await ws.receive_text()   # wait for any client ping / close frame
    except WebSocketDisconnect:
        manager.disconnect(ws)
