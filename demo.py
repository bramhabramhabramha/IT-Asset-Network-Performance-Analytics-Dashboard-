import urllib.request, json
from collections import Counter

BASE = 'http://localhost:8000'

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path).read())

# ── 1. Bust the TTL cache so fresh data is read from CSVs immediately
from modules.ingestor import invalidate_cache
invalidate_cache()
print("Cache cleared — reading fresh data from CSVs\n")

# ── 2. Assets Overview
assets = get('/api/assets?limit=100')
total  = assets["total"]
print(f"=== ASSETS  ({total} total) ===")
for a in assets["items"][-5:]:   # newest 5
    print(f"  {a['asset_id']}  {a['name']:<32}  {a['status']:<12}  {a['location']}")

# ── 3. Network Uptime Stats
stats = get('/api/uptime/stats')
print("\n=== NETWORK UPTIME STATS ===")
print(f"  Total records    : {stats['total_records']}")
print(f"  Mean uptime      : {stats['mean_uptime']} h")
print(f"  Fleet availability: {stats['overall_uptime_pct']} %")
print(f"  Std deviation    : {stats['std_deviation']} h")
print(f"  Min / Max        : {stats['min_uptime']} h / {stats['max_uptime']} h")

# ── 4. Anomaly Detection
anom = get('/api/uptime/anomalies?z_threshold=2.0')
print(f"\n=== ANOMALIES DETECTED: {anom['count']} (at 2.0 sigma) ===")
for a in anom["anomalies"]:
    sev  = a["severity"].upper()
    name = a["node_name"]
    up   = a["uptime_hours"]
    z    = a["z_score"]
    print(f"  [{sev:<8}]  {name:<22}  uptime={up}h   z={z}")

# ── 5. Node Reliability Tiers
rel   = get('/api/uptime/reliability')
nodes = rel["nodes"]
tiers = Counter(n["reliability"] for n in nodes)
print(f"\n=== RELIABILITY TIERS ({len(nodes)} unique nodes) ===")
for tier in ["excellent", "good", "fair", "poor"]:
    bar = "#" * tiers.get(tier, 0)
    print(f"  {tier:<10}: {tiers.get(tier,0):>2}  {bar}")

# ── 6. Top Failing Assets
fail = get('/api/maintenance/failures')
print(f"\n=== TOP FAILING ASSETS ({fail['count']} assets with incidents) ===")
for f in fail["failure_frequency"][:6]:
    name = str(f["name"] or f["asset_id"])
    print(f"  {f['asset_id']}  {name:<30}  {f['failure_count']} incidents  {f['unresolved']} open")

# ── 7. Asset Type Breakdown
types = get('/api/assets/types')
print("\n=== ASSETS BY TYPE ===")
for t in types:
    bar = "#" * t["count"]
    print(f"  {t['type']:<15}  {t['count']:>2}  {bar}")

# ── 8. Daily Uptime Trend
trend = get('/api/uptime/trend')
print("\n=== DAILY UPTIME TREND ===")
for row in trend["trend"]:
    bar = "#" * int(row["mean_uptime"])
    print(f"  {row['date']}  {row['mean_uptime']:>5}h  {bar}")

print("\nDone — all data is live from the API!")
