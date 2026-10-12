#!/usr/bin/env python3
"""Seed SAMPLE data for the ITOps Resolution Intelligence POC.
NOTE: all data here is synthetic sample data; all actions in the app are simulated."""
import os, sqlite3, datetime as dt
import duckdb

os.makedirs("data", exist_ok=True)
DB = "data/ops.db"
HIST = "data/history.duckdb"
for f in (DB, HIST):
    if os.path.exists(f):
        os.remove(f)
now = dt.datetime.now().replace(second=0, microsecond=0)

con = sqlite3.connect(DB)
c = con.cursor()
c.executescript("""
CREATE TABLE services(id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT);
CREATE TABLE edges(src TEXT, rel TEXT, dst TEXT);
CREATE TABLE incidents(id TEXT PRIMARY KEY, title TEXT, service_id TEXT, priority TEXT, status TEXT,
                       created_at TEXT, summary TEXT, stage TEXT, owner_team TEXT, blocker TEXT,
                       confirmed_cause TEXT);
CREATE TABLE changes(id TEXT PRIMARY KEY, service_id TEXT, description TEXT, deployed_at TEXT, owner TEXT);
CREATE TABLE metrics(id TEXT PRIMARY KEY, service_id TEXT, metric TEXT, value REAL, threshold REAL, ts TEXT);
CREATE TABLE tickets(id TEXT PRIMARY KEY, incident_id TEXT, service_id TEXT, title TEXT, status TEXT,
                     assignee TEXT, created_at TEXT, acceptance TEXT, fix_hint TEXT);
CREATE TABLE kpis(id TEXT PRIMARY KEY, business_service TEXT, metric TEXT, unit TEXT,
                  baseline REAL, current REAL);

-- ---------- DataOps domain (separate model; not forced into the IT incident schema) ----------
CREATE TABLE pipelines(id TEXT PRIMARY KEY, name TEXT, owner_team TEXT, criticality TEXT,
                       schedule TEXT, freshness_sla_min INT);
CREATE TABLE dop_datasets(id TEXT PRIMARY KEY, name TEXT, layer TEXT, owner_team TEXT);
CREATE TABLE dop_lineage(src TEXT, dst TEXT);                       -- upstream dataset -> downstream
CREATE TABLE pipeline_io(pipeline_id TEXT, dataset_id TEXT, direction TEXT);  -- produces | reads
CREATE TABLE dop_runs(id TEXT PRIMARY KEY, pipeline_id TEXT, status TEXT, started_at TEXT,
                      duration_min REAL, rows INT, error TEXT);
CREATE TABLE dop_dq(id TEXT PRIMARY KEY, dataset_id TEXT, rule TEXT, value REAL, threshold REAL);
CREATE TABLE dop_freshness(dataset_id TEXT PRIMARY KEY, last_updated TEXT, sla_min INT);
CREATE TABLE dop_contracts(id TEXT PRIMARY KEY, dataset_id TEXT, name TEXT, version TEXT, owner TEXT);
CREATE TABLE dop_consumers(dataset_id TEXT, consumer TEXT);
CREATE TABLE dop_incidents(id TEXT PRIMARY KEY, title TEXT, pipeline_id TEXT, dataset_id TEXT,
                           priority TEXT, status TEXT, created_at TEXT, stage TEXT, owner_team TEXT,
                           blocker TEXT, confirmed_cause TEXT, summary TEXT);
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

# id, title, service, priority, status, created, summary, stage, owner, blocker, confirmed_cause
incidents = [
    ("INC-8841", "Payment API errors up / checkout slow", "its_payment_api", "P2", "open",
     (now - dt.timedelta(minutes=48)).isoformat(timespec="minutes"),
     "Payment failures up 8%; API latency +42%; DB connection saturation; no broader impact yet.",
     "Fix in progress", "Platform Engineering", "DB connection validation pending", ""),
    ("INC-8802", "Checkout latency after deploy", "app_checkout", "P2", "closed",
     (now - dt.timedelta(days=6)).isoformat(timespec="minutes"),
     "Latency spike after deployment; connection pool exhausted.",
     "Closed", "Checkout Team", "", "CHG-app"),
    ("INC-8711", "DB connection pool exhaustion", "db_payments", "P3", "closed",
     (now - dt.timedelta(days=14)).isoformat(timespec="minutes"),
     "Connection pool exhaustion caused API timeouts.",
     "Closed", "DBA Team", "", ""),
    ("INC-8655", "Payment service deployment rollback", "its_payment_api", "P1", "closed",
     (now - dt.timedelta(days=21)).isoformat(timespec="minutes"),
     "Bad deployment caused payment failures; rolled back.",
     "Closed", "Platform Engineering", "", ""),
]
c.executemany("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?,?)", incidents)

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

kpis = [
    ("K1", "bs_payments", "checkout_success_pct", "%", 98.5, 90.0),
]
c.executemany("INSERT INTO kpis VALUES(?,?,?,?,?,?)", kpis)

# ---------- DataOps data ----------
pipelines = [
    ("P-ORD", "orders_bronze_ingest", "Data Platform", "high", "every 15m", 30),
    ("P-CUST", "customer_360_build", "Analytics Engineering", "high", "hourly", 60),
    ("P-PAY", "payments_gold_agg", "Finance Data", "critical", "every 15m", 15),
]
c.executemany("INSERT INTO pipelines VALUES(?,?,?,?,?,?)", pipelines)

datasets = [
    ("ds_ord_bz", "orders_bronze", "bronze", "Data Platform"),
    ("ds_ord_sv", "orders_silver", "silver", "Analytics Engineering"),
    ("ds_ord_gd", "orders_gold", "gold", "Analytics Engineering"),
    ("ds_cust_bz", "customer_bronze", "bronze", "Data Platform"),
    ("ds_cust_sv", "customer_silver", "silver", "Analytics Engineering"),
    ("ds_cust_360", "customer_360", "gold", "Analytics Engineering"),
    ("ds_pay_bz", "payments_bronze", "bronze", "Finance Data"),
    ("ds_pay_gd", "payments_gold", "gold", "Finance Data"),
]
c.executemany("INSERT INTO dop_datasets VALUES(?,?,?,?)", datasets)

lineage = [
    ("ds_ord_bz", "ds_ord_sv"), ("ds_ord_sv", "ds_ord_gd"),
    ("ds_cust_bz", "ds_cust_sv"), ("ds_cust_sv", "ds_cust_360"),
    ("ds_pay_bz", "ds_pay_gd"),
]
c.executemany("INSERT INTO dop_lineage VALUES(?,?)", lineage)

pipeline_io = [
    ("P-ORD", "ds_ord_bz", "produces"),
    ("P-CUST", "ds_cust_bz", "reads"), ("P-CUST", "ds_cust_360", "produces"),
    ("P-PAY", "ds_pay_bz", "reads"), ("P-PAY", "ds_pay_gd", "produces"),
]
c.executemany("INSERT INTO pipeline_io VALUES(?,?,?)", pipeline_io)

runs = [
    ("R-9001", "P-ORD", "failed", (now - dt.timedelta(minutes=35)).isoformat(timespec="minutes"), 3.0, 0,
     "SCHEMA_MISMATCH: unexpected column 'region_code' in source"),
    ("R-9000", "P-ORD", "success", (now - dt.timedelta(minutes=50)).isoformat(timespec="minutes"), 4.2, 118400, ""),
    ("R-9101", "P-PAY", "success", (now - dt.timedelta(minutes=48)).isoformat(timespec="minutes"), 26.0, 220100, ""),
    ("R-9100", "P-PAY", "success", (now - dt.timedelta(minutes=30)).isoformat(timespec="minutes"), 9.0, 220300, ""),
    ("R-9200", "P-CUST", "success", (now - dt.timedelta(minutes=40)).isoformat(timespec="minutes"), 12.0, 54000, ""),
]
c.executemany("INSERT INTO dop_runs VALUES(?,?,?,?,?,?,?)", runs)

dop_dq = [
    ("DQ-1", "ds_cust_360", "null_customer_id_pct", 6.0, 1.0),
    ("DQ-2", "ds_ord_gd", "reconciliation_variance_pct", 0.2, 0.5),
    ("DQ-3", "ds_pay_gd", "row_count_drift_pct", 3.0, 10.0),
]
c.executemany("INSERT INTO dop_dq VALUES(?,?,?,?,?)", dop_dq)

dop_fresh = [
    ("ds_ord_bz", (now - dt.timedelta(minutes=40)).isoformat(timespec="minutes"), 30),
    ("ds_ord_gd", (now - dt.timedelta(minutes=45)).isoformat(timespec="minutes"), 60),
    ("ds_cust_360", (now - dt.timedelta(minutes=70)).isoformat(timespec="minutes"), 60),
    ("ds_pay_gd", (now - dt.timedelta(minutes=45)).isoformat(timespec="minutes"), 15),
]
c.executemany("INSERT INTO dop_freshness VALUES(?,?,?)", dop_fresh)

dop_contracts = [
    ("DC-1", "ds_ord_bz", "orders_bronze", "v3", "Data Platform"),
    ("DC-2", "ds_cust_360", "customer_360", "v5", "Analytics Engineering"),
    ("DC-3", "ds_pay_gd", "payments_gold", "v2", "Finance Data"),
]
c.executemany("INSERT INTO dop_contracts VALUES(?,?,?,?,?)", dop_contracts)

consumers = [
    ("ds_ord_gd", "Ops reporting"), ("ds_ord_gd", "Revenue dashboard"),
    ("ds_cust_360", "CSM 360"), ("ds_cust_360", "Marketing"),
    ("ds_pay_gd", "Finance close"), ("ds_pay_gd", "Payments KPI"),
]
c.executemany("INSERT INTO dop_consumers VALUES(?,?)", consumers)

dop_incidents = [
    ("DOP-1001", "orders_bronze ingestion failed — source schema drift", "P-ORD", "ds_ord_bz", "P2", "open",
     (now - dt.timedelta(minutes=34)).isoformat(timespec="minutes"), "Fix in progress", "Data Platform",
     "Upstream schema drift not reconciled in contract", "",
     "Run R-9001 failed with SCHEMA_MISMATCH (new column 'region_code'); downstream orders_gold is stale."),
    ("DOP-1002", "customer_360 data-quality breach — null keys spike", "P-CUST", "ds_cust_360", "P2", "open",
     (now - dt.timedelta(hours=2)).isoformat(timespec="minutes"), "Diagnosed", "Analytics Engineering",
     "Null customer_id at 6% (> 1% rule)", "",
     "DQ rule null_customer_id_pct breached at 6% (threshold 1%); customer_360 is consumed by CSM 360 and Marketing."),
    ("DOP-1003", "payments_gold freshness SLA breach", "P-PAY", "ds_pay_gd", "P1", "open",
     (now - dt.timedelta(minutes=45)).isoformat(timespec="minutes"), "Change raised", "Finance Data",
     "Upstream backlog delaying the aggregation job", "",
     "Freshness is 45m against a 15m SLA; Finance close depends on payments_gold."),
]
c.executemany("INSERT INTO dop_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", dop_incidents)

con.commit()
con.close()

# KPI history (DuckDB) — keyed by metric so it can be scenario-specific
d = duckdb.connect(HIST)
d.execute("CREATE TABLE kpi(ts TIMESTAMP, metric VARCHAR, value DOUBLE, scenario VARCHAR)")
rows = []
base = now - dt.timedelta(hours=6)
for i in range(37):
    t = base + dt.timedelta(minutes=10 * i)
    cur = 98.5 if t < now - dt.timedelta(hours=1) else 90.0
    rows.append((t, "checkout_success_pct", cur, "current"))
    rows.append((t, "checkout_success_pct", 98.5, "fixed"))
d.executemany("INSERT INTO kpi VALUES(?,?,?,?)", rows)
d.close()
print("Seeded sample data (data/ops.db + data/history.duckdb) — synthetic, all actions simulated")
