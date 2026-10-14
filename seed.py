#!/usr/bin/env python3
"""Seed SAMPLE data for the Resolution Intelligence POC.

ONE connected story across two domains:
  core_ledger source schema change  →  payments_bronze_ingest pipeline FAILS (schema drift)
  →  payments_gold is stale  →  the customer-facing payment service serves stale risk data
  →  business incident (INC-8841) on the Payments service.

All data is synthetic; all actions are simulated."""
import os, sqlite3, datetime as dt
import duckdb

os.makedirs("data", exist_ok=True)
DB = "data/ops.db"
HIST = "data/history.duckdb"
for f in (DB, HIST):
    if os.path.exists(f):
        os.remove(f)
now = dt.datetime.now().replace(second=0, microsecond=0)
M = lambda mins: (now - dt.timedelta(minutes=mins)).isoformat(timespec="minutes")

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
CREATE TABLE service_data(service_id TEXT, dataset_id TEXT);   -- which dataset a service consumes

-- DataOps domain
CREATE TABLE pipelines(id TEXT PRIMARY KEY, name TEXT, owner_team TEXT, criticality TEXT,
                       schedule TEXT, freshness_sla_min INT);
CREATE TABLE dop_datasets(id TEXT PRIMARY KEY, name TEXT, layer TEXT, owner_team TEXT);
CREATE TABLE dop_lineage(src TEXT, dst TEXT);
CREATE TABLE pipeline_io(pipeline_id TEXT, dataset_id TEXT, direction TEXT);
CREATE TABLE dop_runs(id TEXT PRIMARY KEY, pipeline_id TEXT, status TEXT, started_at TEXT,
                      duration_min REAL, rows INT, error TEXT);
CREATE TABLE dop_dq(id TEXT PRIMARY KEY, dataset_id TEXT, rule TEXT, value REAL, threshold REAL);
CREATE TABLE dop_freshness(dataset_id TEXT PRIMARY KEY, last_updated TEXT, sla_min INT);
CREATE TABLE dop_contracts(id TEXT PRIMARY KEY, dataset_id TEXT, name TEXT, version TEXT, owner TEXT);
CREATE TABLE dop_consumers(dataset_id TEXT, consumer TEXT);
CREATE TABLE dop_incidents(id TEXT PRIMARY KEY, title TEXT, pipeline_id TEXT, dataset_id TEXT,
                           priority TEXT, status TEXT, created_at TEXT, stage TEXT, owner_team TEXT,
                           blocker TEXT, confirmed_cause TEXT, summary TEXT);

-- shared
CREATE TABLE timeline(id TEXT PRIMARY KEY, ref_id TEXT, domain TEXT, ts TEXT, kind TEXT, detail TEXT);
CREATE TABLE correlations(id TEXT PRIMARY KEY, it_id TEXT, dop_id TEXT, shared_cause TEXT, note TEXT);
CREATE TABLE thread_edges(id TEXT PRIMARY KEY, thread_ref TEXT, src TEXT, dst TEXT, rel TEXT,
                          kind TEXT, source TEXT, ts TEXT, confidence TEXT);

-- real-time / collaboration / delegation
CREATE TABLE live_events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, domain TEXT, severity TEXT,
                         source TEXT, message TEXT, ref_id TEXT);
CREATE TABLE comments(id INTEGER PRIMARY KEY AUTOINCREMENT, ref_id TEXT, author TEXT, role TEXT,
                      text TEXT, ts TEXT);
CREATE TABLE delegations(id INTEGER PRIMARY KEY AUTOINCREMENT, ref_id TEXT, frm TEXT, to_ TEXT,
                         action TEXT, status TEXT, ts TEXT);
CREATE TABLE notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, ref_id TEXT, text TEXT,
                           ts TEXT, read INTEGER DEFAULT 0);
-- OLA = internal Operational Level Agreement per owning team (distinct from the customer SLA)
CREATE TABLE olas(team TEXT PRIMARY KEY, response_min INT, restore_min INT);
-- Per-stage OLA targets (configurable) for the resolution thread
CREATE TABLE stage_olas(stage TEXT PRIMARY KEY, target_min INT);
""")

# ------------------------------------------------------------------ IT Ops
services = [
    ("bs_payments",     "Payments",       "business_service", "Payments Ops"),
    ("its_payment_api", "Payment API",    "it_service",       "Platform Engineering"),
    ("app_checkout",    "checkout-api",   "application",      "Checkout Team"),
    ("db_payments",     "payments-db",    "database",         "DBA Team"),
    ("infra_prod",      "prod-cluster",   "infrastructure",   "Cloud Platform"),
]
c.executemany("INSERT INTO services VALUES(?,?,?,?)", services)
edges = [
    ("bs_payments", "supported_by", "its_payment_api"),
    ("its_payment_api", "depends_on", "app_checkout"),
    ("app_checkout", "depends_on", "db_payments"),
    ("app_checkout", "runs_on", "infra_prod"),
]
c.executemany("INSERT INTO edges VALUES(?,?,?)", edges)

# no IT-side change explains this — the trigger is an upstream data change (see DOP-1001)
c.executemany("INSERT INTO changes VALUES(?,?,?,?,?)", [])

incidents = [
    ("INC-8841", "Payment API failures — serving stale risk data", "its_payment_api", "P2", "open",
     M(42), "Payment failures up 8%; the service is using stale risk/limit data; business service Payments at risk.",
     "Diagnosed", "Platform Engineering", "Risk data (payments_gold) is stale", ""),
    ("INC-8802", "Checkout latency after deploy", "app_checkout", "P2", "closed", M(6 * 24 * 60),
     "Latency spike after deployment; connection pool exhausted.", "Closed", "Checkout Team", "", ""),
    ("INC-8711", "DB connection pool exhaustion", "db_payments", "P3", "closed", M(14 * 24 * 60),
     "Connection pool exhaustion caused API timeouts.", "Closed", "DBA Team", "", ""),
    ("INC-8655", "Payment service deployment rollback", "its_payment_api", "P1", "closed", M(21 * 24 * 60),
     "Bad deployment caused payment failures; rolled back.", "Closed", "Platform Engineering", "", ""),
]
c.executemany("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?,?)", incidents)

# competing signals: the real cause (stale data) ranks above a mild DB signal (red herring)
metrics = [
    ("M1", "its_payment_api", "error_rate_pct",      8.1, 1.0,   now.isoformat(timespec="minutes")),
    ("M2", "its_payment_api", "data_age_min",       45.0, 15.0,  now.isoformat(timespec="minutes")),
    ("M3", "db_payments",     "active_connections", 720.0, 700.0, now.isoformat(timespec="minutes")),
]
c.executemany("INSERT INTO metrics VALUES(?,?,?,?,?,?)", metrics)
c.executemany("INSERT INTO service_data VALUES(?,?)",
              [("its_payment_api", "ds_pay_gd"), ("app_checkout", "ds_pay_gd")])

tickets = [
    ("JIRA-5521", "INC-8841", "its_payment_api",
     "Payment service serving stale risk data (upstream payments_gold)",
     "In Progress", "Data Platform", M(20),
     "Payments_gold fresh (≤15 min) and reconciled; payment error rate < 1%.",
     "Restore the upstream feed (payments_bronze_ingest) so payments_gold is fresh again."),
]
c.executemany("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?)", tickets)
kpis = [("K1", "bs_payments", "checkout_success_pct", "%", 98.5, 90.0)]
c.executemany("INSERT INTO kpis VALUES(?,?,?,?,?,?)", kpis)

# ------------------------------------------------------------------ DataOps
pipelines = [
    ("P-PAY-ING", "payments_bronze_ingest", "Data Platform", "critical", "every 15m", 15),
    ("P-PAY-AGG", "payments_gold_agg", "Finance Data", "critical", "every 15m", 15),
]
c.executemany("INSERT INTO pipelines VALUES(?,?,?,?,?,?)", pipelines)

datasets = [
    ("core_ledger", "core_ledger", "source", "Core Banking"),
    ("ds_pay_bz", "payments_bronze", "bronze", "Data Platform"),
    ("ds_pay_sv", "payments_silver", "silver", "Data Platform"),
    ("ds_pay_gd", "payments_gold", "gold", "Finance Data"),
]
c.executemany("INSERT INTO dop_datasets VALUES(?,?,?,?)", datasets)
c.executemany("INSERT INTO dop_lineage VALUES(?,?)",
              [("core_ledger", "ds_pay_bz"), ("ds_pay_bz", "ds_pay_sv"), ("ds_pay_sv", "ds_pay_gd")])
c.executemany("INSERT INTO pipeline_io VALUES(?,?,?)",
              [("P-PAY-ING", "core_ledger", "reads"), ("P-PAY-ING", "ds_pay_bz", "produces"),
               ("P-PAY-AGG", "ds_pay_sv", "reads"), ("P-PAY-AGG", "ds_pay_gd", "produces")])

runs = [
    ("R-9001", "P-PAY-ING", "failed", M(36), 2.0, 0,
     "SCHEMA_MISMATCH: unexpected column 'region_code' in source core_ledger"),
    ("R-9000", "P-PAY-ING", "success", M(51), 3.1, 240500, ""),
    ("R-8801", "P-PAY-AGG", "success", M(40), 6.0, 240100, ""),
]
c.executemany("INSERT INTO dop_runs VALUES(?,?,?,?,?,?,?)", runs)

c.executemany("INSERT INTO dop_dq VALUES(?,?,?,?,?)", [
    ("DQ-1", "ds_pay_gd", "row_count_drift_pct", 1.5, 10.0),
    ("DQ-2", "ds_pay_gd", "reconciliation_variance_pct", 0.3, 0.5),
])
c.executemany("INSERT INTO dop_freshness VALUES(?,?,?)", [
    ("core_ledger", M(5), 15),
    ("ds_pay_bz", M(40), 15),
    ("ds_pay_sv", M(42), 15),
    ("ds_pay_gd", M(45), 15),
])
c.executemany("INSERT INTO dop_contracts VALUES(?,?,?,?,?)", [
    ("DC-1", "ds_pay_bz", "payments_bronze", "v3", "Data Platform"),
    ("DC-2", "ds_pay_gd", "payments_gold", "v2", "Finance Data"),
])
c.executemany("INSERT INTO dop_consumers VALUES(?,?)", [
    ("ds_pay_gd", "Payment service (checkout-api)"), ("ds_pay_gd", "Finance close"),
    ("ds_pay_gd", "Risk & limits"), ("ds_pay_sv", "Fraud analytics"),
])

c.executemany("INSERT INTO dop_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", [
    ("DOP-1001", "payments_bronze_ingest failed — source schema drift", "P-PAY-ING", "ds_pay_bz",
     "P1", "open", M(35), "Diagnosed", "Data Platform",
     "core_ledger added column 'region_code' not reconciled in the contract", "",
     "Run R-9001 failed (SCHEMA_MISMATCH 'region_code'); payments_gold is stale → the payment service "
     "serves stale risk data (business impact)."),
])

# ------------------------------------------------------------------ shared: timeline + correlation
timeline = [
    ("T-1", "DOP-1001", "dataops", M(60), "change", "core_ledger source schema changed — new column 'region_code'"),
    ("T-2", "DOP-1001", "dataops", M(36), "alert", "run R-9001 failed — SCHEMA_MISMATCH 'region_code'"),
    ("T-3", "DOP-1001", "dataops", M(35), "incident", "DOP-1001 raised (P1) — owner Data Platform"),
    ("T-4", "DOP-1001", "dataops", M(45), "impact", "payments_gold stale (45 min > 15 min SLA)"),
    ("T-5", "INC-8841", "itops", M(44), "alert", "Payment API data_age_min 45 > 15 (serving stale risk data)"),
    ("T-6", "INC-8841", "itops", M(43), "alert", "Payment API error_rate_pct 8.1 > 1.0"),
    ("T-7", "INC-8841", "itops", M(42), "incident",
     "ServiceNow: INC-8841 raised (P2) — owner Platform Engineering"),
    ("T-8", "INC-8841", "itops", M(20), "ticket", "Jira: JIRA-5521 defect created for Data Platform"),
]
c.executemany("INSERT INTO timeline VALUES(?,?,?,?,?,?)", timeline)
c.executemany("INSERT INTO correlations VALUES(?,?,?,?,?)", [
    ("CORR-1", "INC-8841", "DOP-1001", "core_ledger schema change (new column 'region_code')",
     "Root cause flows DataOps → IT Ops: the pipeline failure (DOP-1001) left payments_gold stale, so the "
     "customer-facing payment service served stale risk data (INC-8841). Affected business service: Payments."),
])
c.executemany("INSERT INTO thread_edges VALUES(?,?,?,?,?,?,?,?,?)", [
    ("TE-1", "INC-8841", "Schema change (core_ledger)", "Pipeline failure (payments_bronze_ingest)", "caused",
     "observed", "DataOps · run R-9001 SCHEMA_MISMATCH", M(60), "high"),
    ("TE-2", "INC-8841", "Pipeline failure", "payments_gold stale", "→ stale data",
     "observed", "DataOps · freshness 45m > 15m SLA", M(45), "high"),
    ("TE-3", "INC-8841", "payments_gold stale", "Payment API degradation", "→ impacts",
     "inferred", "IT Ops · data_age 45>15 with error_rate 8.1>1 (to validate)", M(44), "medium"),
    ("TE-4", "INC-8841", "DB connection saturation", "Payment API degradation", "contributes",
     "inferred", "IT Ops · active_connections 720>700 (secondary cause)", M(43), "low"),
])

c.executemany("INSERT INTO live_events(ts,domain,severity,source,message,ref_id) VALUES(?,?,?,?,?,?)", [
    (M(12), "dataops", "warning", "payments_gold", "Freshness 45 min > 15 min SLA", "DOP-1001"),
    (M(9), "itops", "info", "monitoring", "Checkout success 90% (baseline 98.5%)", "INC-8841"),
    (M(3), "itops", "warning", "payment-api", "data_age_min 45 > 15 (serving stale risk data)", "INC-8841"),
    (M(2), "dataops", "critical", "payments_bronze_ingest", "run R-9001 FAILED (SCHEMA_MISMATCH 'region_code')", "DOP-1001"),
])
c.executemany("INSERT INTO comments(ref_id,author,role,text,ts) VALUES(?,?,?,?,?)", [
    ("DOP-1001", "Priya (Data Engineer)", "Data Engineer",
     "Confirmed schema drift on core_ledger; drafting contract v4 before replay.", M(15)),
    ("INC-8841", "Amit (Incident Manager)", "Incident Manager",
     "Business impact on Payments — engaging Data Owner and CSM for updates.", M(12)),
])
c.executemany("INSERT INTO delegations(ref_id,frm,to_,action,status,ts) VALUES(?,?,?,?,?,?)", [
    ("DOP-1001", "Data Owner", "Data Engineer", "Reconcile schema (contract v4) + replay", "assigned", M(14)),
])
c.executemany("INSERT INTO notifications(role,ref_id,text,ts,read) VALUES(?,?,?,?,?)", [
    ("Data Engineer", "DOP-1001", "Data Owner delegated to you: Reconcile schema (contract v4) + replay", M(14), 0),
    ("Data Owner", "INC-8841", "Amit (Incident Manager) mentioned you: business impact on Payments", M(12), 0),
])
c.executemany("INSERT INTO olas(team,response_min,restore_min) VALUES(?,?,?)", [
    ("Platform Engineering", 30, 180), ("Checkout Team", 30, 240), ("DBA Team", 15, 120),
    ("Cloud Platform", 30, 240), ("Data Platform", 30, 180), ("Finance Data", 30, 180),
    ("Analytics Engineering", 60, 240),
])
c.executemany("INSERT INTO stage_olas(stage,target_min) VALUES(?,?)", [
    ("Detect", 5), ("Correlate", 15), ("Coordinate", 15), ("Act", 30), ("Verify", 30),
])

con.commit()
con.close()

# KPI history
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
print("Seeded one connected scenario (source schema change → pipeline failure → stale data → business incident).")
