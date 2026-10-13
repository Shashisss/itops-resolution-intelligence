#!/usr/bin/env python3
"""Real-time monitoring — a simulated live event stream (cross-domain)."""
import sqlite3
import datetime as dt
import random

DB = "data/ops.db"
CATALOG = [
    ("itops", "info", "monitoring", "Checkout success holding at 90%", "INC-8841"),
    ("itops", "warning", "payment-api", "p95 latency near threshold", "INC-8841"),
    ("itops", "critical", "payment-api", "error_rate_pct above threshold", "INC-8841"),
    ("dataops", "info", "payments_bronze_ingest", "retry scheduled", "DOP-1001"),
    ("dataops", "warning", "payments_gold", "freshness drift increasing", "DOP-1001"),
    ("dataops", "info", "payments_silver", "upsert progressing", "DOP-1001"),
]
SEV_ICON = {"info": "🟢", "warning": "🟠", "critical": "🔴"}


def recent(limit=14):
    try:
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute("SELECT * FROM live_events ORDER BY id DESC LIMIT ?", (limit,))]
        con.close()
        return rows
    except Exception:
        return []


def tick():
    """Append one simulated event, throttled to at most ~every 5 seconds."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    last = con.execute("SELECT ts FROM live_events ORDER BY id DESC LIMIT 1").fetchone()
    now = dt.datetime.now()
    if last:
        try:
            if (now - dt.datetime.fromisoformat(last["ts"])).total_seconds() < 5:
                con.close()
                return
        except Exception:
            pass
    d, sev, src, msg, ref = random.choice(CATALOG)
    con.execute("INSERT INTO live_events(ts,domain,severity,source,message,ref_id) VALUES(?,?,?,?,?,?)",
                (now.replace(microsecond=0).isoformat(timespec="seconds"), d, sev, src, msg, ref))
    con.commit()
    con.close()
    if sev in ("warning", "critical") and ref:      # link meaningful live events into the incident timeline
        tick_timeline(ref, d, sev, f'live: {src} — {msg}')


def events_last_15min():
    try:
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM live_events WHERE ts >= ?",
                        ((dt.datetime.now() - dt.timedelta(minutes=15)).isoformat(timespec="seconds"),)).fetchone()[0]
        con.close()
        return n
    except Exception:
        return 0


# Deterministic, scripted scenario for replay/fast-forward (the connected story).
REPLAY_SCRIPT = [
    ("dataops", "change", "core_ledger", "source schema change: new column 'region_code'", "DOP-1001"),
    ("dataops", "critical", "payments_bronze_ingest", "run R-9001 FAILED (SCHEMA_MISMATCH 'region_code')", "DOP-1001"),
    ("dataops", "warning", "payments_gold", "freshness 45 min > 15 min SLA", "DOP-1001"),
    ("itops", "warning", "payment-api", "data_age_min 45 > 15 (serving stale risk data)", "INC-8841"),
    ("itops", "critical", "payment-api", "error_rate_pct 8.1 > 1.0", "INC-8841"),
    ("itops", "info", "monitoring", "business impact: checkout success 90% (baseline 98.5%)", "INC-8841"),
    ("dataops", "info", "payments_bronze_ingest", "delegated to Data Engineer: reconcile schema + replay", "DOP-1001"),
    ("dataops", "info", "payments_gold", "repair applied — replaying batch", "DOP-1001"),
    ("itops", "info", "monitoring", "verification recorded — see the incident Verify step for the outcome", "INC-8841"),
]


def clear_events():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM live_events")
    con.commit()
    con.close()


def emit_replay_event(ev):
    d, sev, src, msg, ref = ev
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO live_events(ts,domain,severity,source,message,ref_id) VALUES(?,?,?,?,?,?)",
                (dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds"), d, sev, src, msg, ref))
    con.commit()
    con.close()
    if ref:                                          # one auditable history: link into the incident timeline
        tick_timeline(ref, d, sev, msg)


def tick_timeline(ref_id, domain, severity, message):
    """Push a live event into the durable operational timeline too."""
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO timeline VALUES(?,?,?,?,?,?)",
                (f'RT-{dt.datetime.now().strftime("%H%M%S%f")}', ref_id, domain,
                 dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds"),
                 "alert" if severity in ("warning", "critical") else "detect", message))
    con.commit()
    con.close()
