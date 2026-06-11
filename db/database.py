"""
db/database.py — SQLite persistence layer.

Stores processed analytics snapshots so the dashboard can retrieve
historical results without re-running the full Pandas pipeline each time.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "analytics.db"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode for concurrency safety."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not already exist."""
    conn = get_connection()
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS uptime_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT    NOT NULL,
                payload     TEXT    NOT NULL   -- JSON blob
            );

            CREATE TABLE IF NOT EXISTS anomaly_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT    NOT NULL,
                node_id     TEXT    NOT NULL,
                node_name   TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                uptime_hours REAL   NOT NULL
            );

            CREATE TABLE IF NOT EXISTS failure_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at   TEXT NOT NULL,
                asset_id      TEXT NOT NULL,
                failure_count INTEGER NOT NULL
            );
            """
        )
    conn.close()


def save_uptime_snapshot(stats: dict) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO uptime_snapshots (captured_at, payload) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), json.dumps(stats)),
        )
    conn.close()


def get_uptime_history(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT captured_at, payload FROM uptime_snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"captured_at": r["captured_at"], **json.loads(r["payload"])} for r in rows]


def save_anomalies(anomalies: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    with conn:
        conn.executemany(
            """INSERT INTO anomaly_log (captured_at, node_id, node_name, date, uptime_hours)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (now, a["node_id"], a["node_name"], str(a["date"]), a["uptime_hours"])
                for a in anomalies
            ],
        )
    conn.close()


def save_failures(failures: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    with conn:
        conn.executemany(
            "INSERT INTO failure_log (captured_at, asset_id, failure_count) VALUES (?, ?, ?)",
            [(now, f["asset_id"], f["failure_count"]) for f in failures],
        )
    conn.close()
