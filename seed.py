#!/usr/bin/env python3
"""Seed sample operational data for the ITOps Resolution Intelligence POC.
Creates data/ops.db (operational state) and data/history.duckdb (KPI history)."""
import os, sqlite3, datetime as dt
import duckdb

os.makedirs("data", exist_ok=True)
DB = "data/ops.db"
HIST = "data/history.duckdb"
for f in (DB, HIST):
    if os.path.exists(f):
        os.remove(f)

now = dt.datetime.now().replace(second=0, microsecond=0)

# ---------------- operational state (SQLite) ----------------
con = sqlite3.connect(DB)
c = con.cursor()
c.executescript("""
CREATE TABLE services(id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT);
CREATE TABLE edges(src TEXT, rel TEXT, dst TEXT);
CREATE TABLE incidents(id TEXT PRIMARY KEY, title TEXT, service_id TEXT, priority TEXT,
                       status TEXT, created_at TEXT, summary TEXT);
CREATE TABLE changes(id TEXT PRIMARY KEY, service_id TEXT, description TEXT, deployed_at TEXT, owner TEXT);
CREATE TABLE metrics(id TEXT PRIMARY KEY, service_id TEXT, metric TEXT, value REAL, threshold REAL, ts TEXT);
CREATE TABLE tickets(id TEXT PRIMARY KEY, incident_id TEXT, service_id TEXT, title TEXT, status TEXT,
                     assignee TEXT, created_at TEXT, acceptance TEXT, fix_hint TEXT);
""")

services = [
    ("bs_payments",     "Payments",       "business_service", "Payments Ops"),
    ("its_payment_api", "Payment API",    "it_service",       "Platform Engineering"),
    ("app_checkout",    "checkout-api",   "application",      "Checkout Team"),
    ("db_payments",     "payments-db",    "database",         "DBA Team"),
    ("infra_prod",      "prod-cluster",   "infrastructure",   "Cloud Platform"),
]
c.executemany("INSERT INTO services VALUES(?,?,?,?)", services)

edges = [
    ("bs_payments",     "supported_by", "its_payment_api"),
    ("its_payment_api", "depends_on",   "app_checkout"),
    ("app_checkout",    "depends_on",   "db_payments"),
    ("app_checkout",    "runs_on",      "infra_prod"),
]
c.executemany("INSERT INTO edges VALUES(?,?,?)", edges)

changes = [
    ("CHG-1042", "app_checkout", "Deploy checkout-api v1.42 (retry/timeout change)",
     (now - dt.timedelta(hours=2)).isoformat(timespec="minutes"), "Checkout Team"),
    ("CHG-1039", "db_payments", "DB parameter tuning",
     (now - dt.timedelta(days=3)).isoformat(timespec="minutes"), "DBA Team"),
]
c.executemany("INSERT INTO changes VALUES(?,?,?,?,?)", changes)

incidents = [
    ("INC-8841", "Payment API errors up / checkout slow", "its_payment_api", "P2", "open",
     (now - dt.timedelta(minutes=48)).isoformat(timespec="minutes"),
     "Payment failures up 8%; API latency +42%; DB connection saturation; no broader impact yet."),
    ("INC-8802", "Checkout latency after deploy", "app_checkout", "P2", "closed",
     (now - dt.timedelta(days=6)).isoformat(timespec="minutes"),
     "Latency spike after deployment; connection pool exhausted."),
    ("INC-8711", "DB connection pool exhaustion", "db_payments", "P3", "closed",
     (now - dt.timedelta(days=14)).isoformat(timespec="minutes"),
     "Connection pool exhaustion caused API timeouts."),
    ("INC-8655", "Payment service deployment rollback", "its_payment_api", "P1", "closed",
     (now - dt.timedelta(days=21)).isoformat(timespec="minutes"),
     "Bad deployment caused payment failures; rolled back."),
]
c.executemany("INSERT INTO incidents VALUES(?,?,?,?,?,?,?)", incidents)

metrics = [
    ("M1", "db_payments",     "cpu_pct",            94.0, 80.0,  now.isoformat(timespec="minutes")),
    ("M2", "db_payments",     "active_connections", 980.0, 700.0, now.isoformat(timespec="minutes")),
    ("M3", "its_payment_api", "p95_latency_ms",     640.0, 300.0, now.isoformat(timespec="minutes")),
    ("M4", "app_checkout",    "error_rate_pct",      8.1, 1.0,   now.isoformat(timespec="minutes")),
]
c.executemany("INSERT INTO metrics VALUES(?,?,?,?,?,?)", metrics)

tickets = [
    ("JIRA-5521", "INC-8841", "app_checkout",
     "checkout-api: connection pool exhaustion under retry storm",
     "In Progress", "Checkout Team", (now - dt.timedelta(minutes=25)).isoformat(timespec="minutes"),
     "Pool must not exhaust under retry; p95 latency < 300ms; error rate < 1%.",
     "Tune pool size + backoff; guard retry amplification; stay under payments-db connection cap."),
    ("JIRA-5488", "INC-8711", "db_payments",
     "payments-db: connection leak on long-running transactions",
     "Done", "DBA Team", (now - dt.timedelta(days=13)).isoformat(timespec="minutes"),
     "No connection growth over a 24h soak test.",
     "Audit long-running transactions; enforce statement timeout."),
]
c.executemany("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?)", tickets)
con.commit()
con.close()

# ---------------- KPI history (DuckDB) ----------------
d = duckdb.connect(HIST)
d.execute("CREATE TABLE kpi(ts TIMESTAMP, metric VARCHAR, value DOUBLE, scenario VARCHAR)")
rows = []
base = now - dt.timedelta(hours=6)
for i in range(37):
    t = base + dt.timedelta(minutes=10 * i)
    current = 98.5 if t < now - dt.timedelta(hours=1) else 90.0
    rows.append((t, "checkout_success_pct", current, "current"))
    rows.append((t, "checkout_success_pct", 98.5, "fixed"))
d.executemany("INSERT INTO kpi VALUES(?,?,?,?)", rows)
d.close()
print("Seeded data/ops.db and data/history.duckdb")
