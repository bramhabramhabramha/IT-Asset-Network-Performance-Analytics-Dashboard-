# IT Asset & Network Performance Analytics Dashboard

> **REST API built with FastAPI serving real-time IT analytics** — Pandas pipelines for multi-source CSV ingestion and normalization, NumPy statistical engine for uptime trend analysis and anomaly detection, and automated summary reports across 100+ simulated enterprise nodes.

---

## ✨ Features

| Category | Details |
|---|---|
| **API** | 14 FastAPI REST endpoints with Swagger docs at `/docs` |
| **Data Pipeline** | Pandas — CSV ingestion, cleaning, type coercion, derived columns |
| **Analytics** | NumPy — descriptive stats, Z-score anomaly detection, histograms |
| **Persistence** | SQLite (WAL mode) — historical uptime snapshots & anomaly log |
| **Dashboard** | Single-page HTML/JS dashboard with Chart.js visualizations |

---

## 🏗 Project Structure

```
it-asset-dashboard/
├── main.py                  # FastAPI app — 14 REST endpoints
├── data/
│   ├── assets.csv           # 30 hardware assets inventory
│   ├── network_uptime.csv   # 100+ node uptime records
│   └── maintenance_logs.csv # 30 incident records
├── modules/
│   ├── ingestor.py          # Pandas loading & cleaning pipeline
│   ├── analytics.py         # NumPy stats & anomaly detection
│   └── reports.py           # Automated summary report generator
├── db/
│   └── database.py          # SQLite connection & persistence
├── static/
│   └── dashboard.html       # Premium browser UI (Chart.js)
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
uvicorn main:app --reload

# 3. Open the dashboard
http://localhost:8000/

# 4. Explore the interactive Swagger API docs
http://localhost:8000/docs

# 5. Run the console analytics demonstration
python demo.py
```

---

## 📡 API Endpoints

### Assets
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/assets` | All assets (filterable by `?status=Active`) |
| `GET` | `/api/assets/types` | Asset count by type |
| `GET` | `/api/assets/locations` | Asset count by location |
| `GET` | `/api/assets/age` | NumPy histogram of asset ages |

### Network
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/uptime/stats` | Descriptive stats (mean, std, percentiles) |
| `GET` | `/api/uptime/anomalies` | Z-score anomaly detection (`?z_threshold=2.0`) |
| `GET` | `/api/uptime/reliability` | Node reliability tier ranking |
| `GET` | `/api/uptime/trend` | Daily mean uptime for time-series charts |
| `GET` | `/api/uptime/history` | Historical snapshots from SQLite |

### Maintenance
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/maintenance/logs` | All logs (filterable by `?resolved=true`) |
| `GET` | `/api/maintenance/failures` | Failure frequency per asset |

### Reports
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/report/summary` | Full analytics report (JSON) |

### Uploads
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload/assets` | Upload and replace assets dataset (validates columns) |
| `POST` | `/api/upload/uptime` | Upload and replace network uptime dataset (validates columns) |
| `POST` | `/api/upload/maintenance` | Upload and replace maintenance logs dataset (validates columns) |

### WebSockets
| Protocol | Endpoint | Description |
|---|---|---|
| `WS` | `/ws/live` | Stream real-time network uptime stats & anomaly counts every 5s |

---

## 🔬 Technical Highlights

### Pandas Pipeline (`modules/ingestor.py`)
- Column name normalization (strip, lowercase, underscore)
- Type coercion with `errors="coerce"` for safe parsing
- Null row removal on critical columns
- Derived columns: `age_days`, `uptime_pct`

### NumPy Analytics Engine (`modules/analytics.py`)
- **Descriptive stats**: mean, median, min, max, std, variance, IQR
- **Z-score anomaly detection**: configurable threshold (default 2σ)
- **Severity classification**: critical / high / medium via Z-score bins
- **Age distribution**: `np.histogram()` for charting
- **Node reliability tiers**: excellent / good / fair / poor

### SQLite Persistence (`db/database.py`)
- WAL journal mode for concurrent read safety
- Uptime snapshot history (queryable with `?limit=N`)
- Anomaly log with timestamp tracking
- Failure frequency history



## 🛠 Tech Stack

- **Python 3.10+**
- **FastAPI** — REST API framework
- **Uvicorn** — ASGI server
- **Pandas** — data ingestion and cleaning
- **NumPy** — statistical analysis and anomaly detection
- **SQLite** — lightweight persistence (no setup needed)
- **Chart.js** — dashboard visualizations
