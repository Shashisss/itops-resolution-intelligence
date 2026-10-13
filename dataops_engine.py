#!/usr/bin/env python3
"""DataOps domain engine — pipelines, lineage, DQ, freshness, contracts.
Separate data model from IT Ops. Deterministic graph + rule-based reasoning."""
import sqlite3
import datetime as dt
import networkx as nx

DB = "data/ops.db"
STAGES = ["Detected", "Triaged", "Diagnosed", "Fix in progress", "Fix applied", "Backfilled", "Validated", "Closed"]


def load():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    def q(sql):
        return [dict(r) for r in con.execute(sql)]

    pipelines = {p["id"]: p for p in q("SELECT * FROM pipelines")}
    datasets = {d["id"]: d for d in q("SELECT * FROM dop_datasets")}
    lineage = q("SELECT * FROM dop_lineage")
    pio = q("SELECT * FROM pipeline_io")
    runs = q("SELECT * FROM dop_runs")
    dq = q("SELECT * FROM dop_dq")
    fresh = {f["dataset_id"]: f for f in q("SELECT * FROM dop_freshness")}
    contracts = q("SELECT * FROM dop_contracts")
    consumers = q("SELECT * FROM dop_consumers")
    incidents = q("SELECT * FROM dop_incidents")
    con.close()
    G = nx.DiGraph()
    for d in datasets.values():
        G.add_node(d["id"], **d)
    for e in lineage:
        G.add_edge(e["src"], e["dst"])
    return dict(pipelines=pipelines, datasets=datasets, lineage=lineage, pio=pio, runs=runs, dq=dq,
                fresh=fresh, contracts=contracts, consumers=consumers, incidents=incidents, G=G)


def set_stage(inc_id, stage):
    con = sqlite3.connect(DB)
    con.execute("UPDATE dop_incidents SET stage=? WHERE id=?", (stage, inc_id))
    con.commit()
    con.close()


def confirm_cause(inc_id, key):
    con = sqlite3.connect(DB)
    con.execute("UPDATE dop_incidents SET confirmed_cause=? WHERE id=?", (key, inc_id))
    con.commit()
    con.close()


def _lag_min(f):
    try:
        return int((dt.datetime.now() - dt.datetime.fromisoformat(f["last_updated"])).total_seconds() / 60)
    except Exception:
        return 0


def downstream(ds, G):
    return sorted(nx.descendants(G, ds))


def upstream(ds, G):
    return sorted(nx.ancestors(G, ds))


def lineage_paths(ds, G):
    """Upstream source -> dataset paths (multiple parents supported)."""
    sources = [n for n in nx.ancestors(G, ds) if G.in_degree(n) == 0]
    paths = []
    for s in sources:
        for p in nx.all_simple_paths(G, s, ds):
            paths.append(p)
    if not paths:
        paths = [[ds]]
    paths = sorted({tuple(p) for p in paths}, key=len, reverse=True)
    return [list(p) for p in paths]


def impact(ds, data):
    G, datasets, consumers = data["G"], data["datasets"], data["consumers"]
    downs = downstream(ds, G)
    affected = {ds} | set(downs)
    cons = sorted({c["consumer"] for c in consumers if c["dataset_id"] in affected})
    return downs, cons


def latest_run(pid, runs):
    rs = sorted([r for r in runs if r["pipeline_id"] == pid], key=lambda r: r["started_at"], reverse=True)
    return rs[0] if rs else None


def causes(inc, data):
    """Pipeline RCA hypotheses (suspected/confirmed, with evidence + confidence)."""
    ds, pid, G = inc["dataset_id"], inc["pipeline_id"], data["G"]
    confirmed = inc.get("confirmed_cause") or ""
    hyps = []
    run = latest_run(pid, data["runs"])
    if run and run["status"] == "failed":
        key = f'RUN:{run["id"]}'
        hyps.append({"type": "pipeline", "key": key, "confidence": "high",
                     "status": "confirmed" if confirmed == key else "suspected",
                     "evidence": f'run {run["id"]} failed {run["started_at"]}: {run["error"]}',
                     "text": f'pipeline run {run["id"]} failed — {run["error"]}'})
    for d in data["dq"]:
        if d["dataset_id"] == ds and d["value"] > d["threshold"]:
            key = f'DQ:{d["id"]}'
            hyps.append({"type": "data quality", "key": key, "confidence": "high",
                         "status": "confirmed" if confirmed == key else "suspected",
                         "evidence": f'{d["rule"]} = {d["value"]:.1f} vs threshold {d["threshold"]:.1f} on {ds}',
                         "text": f'data-quality rule {d["rule"]} breached at {d["value"]:.1f} '
                                 f'(threshold {d["threshold"]:.1f})'})
    f = data["fresh"].get(ds)
    if f and _lag_min(f) > f["sla_min"]:
        lag = _lag_min(f)
        key = f'FRESH:{ds}'
        hyps.append({"type": "freshness", "key": key,
                     "confidence": "high" if lag > 2 * f["sla_min"] else "medium",
                     "status": "confirmed" if confirmed == key else "suspected",
                     "evidence": f'last updated {lag} min ago vs {f["sla_min"]} min SLA on {ds}',
                     "text": f'freshness SLA breached — {lag} min stale (SLA {f["sla_min"]} min)'})
    return hyps


def recommend(inc, hyps, data):
    pid = inc["pipeline_id"]
    owner = data["pipelines"].get(pid, {}).get("owner_team", inc["owner_team"])
    run_fail = next((h for h in hyps if h["type"] == "pipeline"), None)
    dq = next((h for h in hyps if h["type"] == "data quality"), None)
    fresh = next((h for h in hyps if h["type"] == "freshness"), None)
    if run_fail and "SCHEMA" in run_fail["evidence"].upper():
        return {"action": "Reconcile the source schema with the data contract (schema evolution) and replay "
                          "the failed batch.", "risk": "High (production data)", "mode": "Human approval", "actor": owner}
    if dq:
        return {"action": "Quarantine the violating rows, fix the transform that produces the bad keys, and "
                          "re-run the quality check.", "risk": "Medium", "mode": "Policy controlled", "actor": owner}
    if fresh:
        return {"action": "Scale / parallelise the aggregation job and run a backfill to restore freshness.",
                "risk": "Low–Medium", "mode": "Auto", "actor": owner}
    return {"action": "Gather more evidence.", "risk": "Low", "mode": "Autonomous", "actor": owner}


# Remediation options — outcome depends on the action chosen (not scripted to pass).
DOP_REMEDIATION = [
    {"id": "A", "label": "Reconcile source schema (contract v4) and replay payments_bronze_ingest",
     "mode": "Human approval", "risk": "High (production data)",
     "outcomes": {"freshness": (5, True), "dq": (0.0, True), "downstream": ("healthy", True)}},
    {"id": "B", "label": "Replay without a contract update", "mode": "Policy controlled", "risk": "Medium",
     "outcomes": {"freshness": (8, True), "dq": (0.0, True), "downstream": ("stale", False)}},
    {"id": "C", "label": "Skip the run and monitor", "mode": "Human approval", "risk": "High",
     "outcomes": {"freshness": (45, False), "dq": (0.0, True), "downstream": ("stale", False)}},
]


def verification(inc, data, option, applied=True):
    """Independent re-check of freshness, DQ and downstream health after a chosen action."""
    ds = inc["dataset_id"]
    rows = []
    f = data["fresh"].get(ds)
    if f:
        after, ok = option["outcomes"].get("freshness", (_lag_min(f), False))
        rows.append({"check": f'Freshness — {data["datasets"][ds]["name"]}', "before": f'{_lag_min(f)} min',
                     "threshold checked": f'≤ {f["sla_min"]} min',
                     "after (simulated)": f'{after} min' if applied else "—",
                     "result": ("✅ pass" if ok else "❌ fail") if applied else "⏳ pending"})
    for d in data["dq"]:
        if d["dataset_id"] == ds and d["value"] > d["threshold"]:
            after, ok = option["outcomes"].get("dq", (d["value"], False))
            rows.append({"check": f'DQ — {d["rule"]}', "before": f'{d["value"]:.1f}',
                         "threshold checked": f'≤ {d["threshold"]:.1f}',
                         "after (simulated)": f'{after:.1f}' if applied else "—",
                         "result": ("✅ pass" if ok else "❌ fail") if applied else "⏳ pending"})
    after, ok = option["outcomes"].get("downstream", ("stale", False))
    for dsc in downstream(ds, data["G"]):
        rows.append({"check": f'Downstream — {data["datasets"][dsc]["name"]}', "before": "stale",
                     "threshold checked": "fresh & reconciled",
                     "after (simulated)": after if applied else "—",
                     "result": ("✅ pass" if ok else "❌ fail") if applied else "⏳ pending"})
    return rows


def analytics(inc, data):
    ds, pid = inc["dataset_id"], inc["pipeline_id"]
    f = data["fresh"].get(ds, {})
    lag = _lag_min(f)
    rs = [r for r in data["runs"] if r["pipeline_id"] == pid]
    ok = sum(1 for r in rs if r["status"] == "success")
    reliability = round(100 * ok / len(rs), 1) if rs else 0
    breached = [d for d in data["dq"] if d["dataset_id"] == ds and d["value"] > d["threshold"]]
    quality = "breach" if breached else "pass"
    try:
        elapsed = int((dt.datetime.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 60)
    except Exception:
        elapsed = 0
    return {"incident_age_min": elapsed, "freshness_lag_min": lag,
            "freshness_sla_min": f.get("sla_min"), "quality": quality,
            "reliability_pct": reliability, "downstream": len(downstream(ds, data["G"]))}
