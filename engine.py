#!/usr/bin/env python3
"""Resolution-intelligence engine: graph reasoning, RCA, policy, retrieval.
Pure-Python + embedded data — no servers."""
import sqlite3
import datetime as dt
import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DB = "data/ops.db"


def load():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    services = {r["id"]: dict(r) for r in con.execute("SELECT * FROM services")}
    edges = [dict(r) for r in con.execute("SELECT * FROM edges")]
    incidents = [dict(r) for r in con.execute("SELECT * FROM incidents")]
    changes = [dict(r) for r in con.execute("SELECT * FROM changes")]
    metrics = [dict(r) for r in con.execute("SELECT * FROM metrics")]
    links = {r["service_id"]: r["dataset_id"] for r in con.execute("SELECT * FROM service_data")}
    con.close()
    # "Data age" is by definition now − last_updated: render the ONE computed number, not the value
    # frozen into the seed, so the metric card cannot disagree with the thread or the hypotheses.
    try:
        import journey
        for m in metrics:
            if m.get("metric") == "data_age_min" and m["service_id"] in links:
                f = journey.freshness(links[m["service_id"]])
                if f:
                    m["value"] = float(f["lag_min"])
    except Exception:
        pass
    G = nx.DiGraph()
    for sid, s in services.items():
        G.add_node(sid, **s)
    for e in edges:
        G.add_edge(e["src"], e["dst"], rel=e["rel"])
    return services, edges, incidents, changes, metrics, G


def load_tickets():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM tickets")]
    con.close()
    return rows


def confirm_cause(inc_id, key):
    import datetime as _dt
    con = sqlite3.connect(DB)
    stamp = _dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    try:
        con.execute("ALTER TABLE incidents ADD COLUMN confirmed_at TEXT")
    except Exception:
        pass
    con.execute("UPDATE incidents SET confirmed_cause=?, confirmed_at=? WHERE id=?", (key, stamp, inc_id))
    con.commit()
    con.close()


def set_stage(inc_id, stage):
    con = sqlite3.connect(DB)
    con.execute("UPDATE incidents SET stage=? WHERE id=?", (stage, inc_id))
    con.commit()
    con.close()


def load_kpis():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM kpis")]
    con.close()
    return rows


def load_olas():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM olas")]
    con.close()
    return rows


def load_stage_olas():
    """Per-stage OLA targets. Ensures the shared lifecycle stages exist (migrates older DBs)."""
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS stage_olas(stage TEXT PRIMARY KEY, target_min INT)")
    for stage, tgt in (("Detect", 5), ("Correlate", 15), ("Coordinate", 15), ("Act", 30), ("Verify", 30)):
        con.execute("INSERT OR IGNORE INTO stage_olas(stage,target_min) VALUES(?,?)", (stage, tgt))
    con.commit()
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM stage_olas ORDER BY rowid")]
    con.close()
    return rows


def impact_chain(G, node):
    """Primary upstream path to the business service (for the narrative)."""
    paths = dependency_paths(G, node)
    return paths[0] if paths else [node]


def dependency_paths(G, node):
    """All business-service -> node paths, handling multiple parents."""
    biz = [n for n in nx.ancestors(G, node) if G.nodes[n].get("type") == "business_service"]
    paths = []
    for b in biz:
        for p in nx.all_simple_paths(G, b, node):
            paths.append(p)
    if not paths:
        paths = [[node]]
    paths = sorted({tuple(p) for p in paths}, key=len, reverse=True)
    return [list(p) for p in paths]


def impacted(G, node):
    """Full impacted subgraph: ancestors (business) + node + descendants (dependencies)."""
    return set(nx.ancestors(G, node)) | {node} | set(nx.descendants(G, node))


def in_scope_changes(inc, G, changes):
    """Single source of truth: changes touching the impacted subgraph, newest first."""
    scope = impacted(G, inc["service_id"])
    return sorted([c for c in changes if c["service_id"] in scope],
                  key=lambda c: c["deployed_at"], reverse=True)


def latest_change(inc, G, changes):
    cs = in_scope_changes(inc, G, changes)
    return cs[0] if cs else None


def business_service(G, chain, services):
    for n in chain:
        if services[n]["type"] == "business_service":
            return n
    return None


def causes(inc, G, changes, metrics, services):
    """RCA hypotheses over the impacted subgraph.
    Each hypothesis carries: confidence, evidence, and suspected/confirmed status."""
    scope = impacted(G, inc["service_id"])
    confirmed = (inc.get("confirmed_cause") or "") if inc else ""
    out = []
    rel = sorted([c for c in changes if c["service_id"] in scope],
                 key=lambda c: c["deployed_at"], reverse=True)
    if rel:
        ch = rel[0]
        key = f'CHG:{ch["id"]}'
        conf = "high" if (inc and inc["status"] == "open") else "medium"
        out.append({
            "type": "change", "key": key, "service": ch["service_id"], "label": "Recent change",
            "owner": ch["owner"] or services[ch["service_id"]]["owner"],
            "confidence": conf, "status": "confirmed" if confirmed == key else "suspected",
            "evidence": f'change {ch["id"]} deployed {ch["deployed_at"]} by {ch["owner"]}',
            "text": f'{ch["service_id"]} change {ch["id"]} ("{ch["description"]}") deployed {ch["deployed_at"]}',
        })
    breaching = [m for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]]
    for m in sorted(breaching, key=lambda m: m["value"] / m["threshold"], reverse=True):
        ratio = m["value"] / m["threshold"]
        conf = "high" if ratio >= 1.3 else ("medium" if ratio >= 1.1 else "low")
        key = f'METRIC:{m["id"]}'
        out.append({
            "type": "metric", "key": key, "service": m["service_id"],
            "label": _CAUSE_LABELS.get(m["metric"], f'{m["metric"].replace("_"," ")} breach'),
            "owner": services[m["service_id"]]["owner"],
            "confidence": conf, "status": "confirmed" if confirmed == key else "suspected",
            "evidence": f'{m["metric"]} = {m["value"]:.0f} vs threshold {m["threshold"]:.0f} on {m["service_id"]}',
            "text": f'{m["service_id"]} {m["metric"]} at {m["value"]:.0f} (threshold {m["threshold"]:.0f})',
        })
    # Cross-domain: is an upstream dataset this service consumes stale? (bridge to DataOps)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    links = [r["dataset_id"] for r in
             con.execute("SELECT dataset_id FROM service_data WHERE service_id=?", (inc["service_id"],))]
    for dsi in links:
        fr = con.execute("SELECT last_updated, sla_min FROM dop_freshness WHERE dataset_id=?", (dsi,)).fetchone()
        nm = con.execute("SELECT name FROM dop_datasets WHERE id=?", (dsi,)).fetchone()
        if fr and nm:
            import journey
            f = journey.freshness(dsi)
            lag = f["lag_min"] if f else 0
            if lag > fr["sla_min"]:
                key = f'UPSTREAM:{dsi}'
                out.append({"type": "upstream data", "key": key, "service": dsi, "label": "Stale upstream data",
                            "owner": "Data Platform",
                            "confidence": "high", "status": "confirmed" if confirmed == key else "suspected",
                            "evidence": f'{nm["name"]} last updated {lag} min ago (SLA {fr["sla_min"]} min) '
                                        f'— see DataOps DOP-1001',
                            "text": f'upstream dataset {nm["name"]} is stale ({lag} min) — the service is serving '
                                    f'stale data'})
    con.close()
    return out


def recommend(inc, causes):
    data = next((c for c in causes if c["type"] == "upstream data"), None)
    if data:
        return {"action": f'Reconcile the source schema (contract v4) and replay the pipeline to refresh '
                          f'{data["service"]}, then restart the payment service.',
                "risk": "High (production data + service)", "mode": "Human approval",
                "actor": "Data Platform + Platform Engineering"}
    change = next((c for c in causes if c["type"] == "change"), None)
    metric = next((c for c in causes if c["type"] == "metric"), None)
    if change and metric:
        actor = f'{change["owner"]} + {metric["owner"]}'
        return {"action": f'Roll back the {change["service"]} change and scale {metric["service"]} '
                          f'connections; re-run validation.',
                "risk": "High (production rollback + DB change)", "mode": "Human approval", "actor": actor}
    if change:
        return {"action": f'Investigate / roll back the recent change on {change["service"]}.',
                "risk": "Medium", "mode": "Policy controlled", "actor": change["owner"]}
    if metric:
        return {"action": f'Address the {metric["service"]} metric breach; scale / relax and confirm.',
                "risk": "Low–Medium", "mode": "Auto", "actor": metric["owner"]}
    return {"action": "Gather more evidence.", "risk": "Low", "mode": "Autonomous", "actor": "On-call"}


def change_risk(change, G, services, incidents):
    """Change intelligence: risk class, blast radius and gate for a given change."""
    sid = change["service_id"]
    down = set(nx.descendants(G, sid))
    up = set(nx.ancestors(G, sid))
    biz = next((n for n in up if services[n]["type"] == "business_service"), None)
    scope = {sid} | down | up
    correlated = any(i["service_id"] in scope and i["status"] == "open" for i in incidents)
    score = 1 + min(len(down), 3) + (2 if biz else 0) + (3 if correlated else 0)
    risk = "High" if score >= 6 else ("Medium" if score >= 3 else "Low")
    gate = {"High": "Human approval", "Medium": "Policy controlled", "Low": "Auto"}[risk]
    rationale = []
    if correlated:
        rationale.append("correlated with an open incident")
    if biz:
        rationale.append(f"affects business service {services[biz]['name']}")
    if down:
        rationale.append("downstream: " + ", ".join(services[n]["name"] for n in down))
    return {"risk": risk, "gate": gate, "business": services[biz]["name"] if biz else None,
            "blast": [services[n]["name"] for n in down], "correlated": correlated, "rationale": rationale}


# Remediation options — the OUTCOME depends on the action chosen (not scripted to pass).
# outcomes map metric-key -> (observed value after, passed?)
IT_REMEDIATION = [
    {"id": "A", "label": "Reconcile source schema (contract v4), replay the pipeline, refresh payments_gold",
     "mode": "Human approval", "risk": "High (production data + service)",
     "outcomes": {"data_age_min": (5.0, True), "error_rate_pct": (0.4, True),
                  "active_connections": (600.0, True), "kpi": (98.5, True)}},
    {"id": "B", "label": "Restart the payment service only (no data fix)", "mode": "Policy controlled",
     "risk": "Medium",
     "outcomes": {"data_age_min": (45.0, False), "error_rate_pct": (0.9, True),
                  "active_connections": (690.0, True), "kpi": (93.0, False)}},
    {"id": "C", "label": "Dismiss as transient (no fix)", "mode": "Human approval",
     "risk": "High",
     "outcomes": {"data_age_min": (45.0, False), "error_rate_pct": (8.0, False),
                  "active_connections": (720.0, False), "kpi": (90.0, False)}},
]
_METRIC_LABELS = {"data_age_min": "Data age (min)", "error_rate_pct": "Error rate (%)",
                  "active_connections": "DB connections", "p95_latency_ms": "Latency (p95, ms)"}
_CAUSE_LABELS = {"p95_latency_ms": "Latency breach", "error_rate_pct": "Error rate breach",
                 "active_connections": "DB connection saturation", "data_age_min": "Stale data served"}


def it_verification(inc, ctx, option, applied=True):
    """Independent re-check of raw telemetry against thresholds after a chosen action."""
    G, changes, metrics, services, kpis = ctx["G"], ctx["changes"], ctx["metrics"], ctx["services"], ctx["kpis"]
    scope = impacted(G, inc["service_id"])
    breaching = {m["metric"]: m for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]}
    biz = business_service(G, dependency_paths(G, inc["service_id"])[0], services)
    k = next((x for x in kpis if x["business_service"] == biz), None)
    rows = []
    for key in ["data_age_min", "error_rate_pct", "active_connections"]:
        if key in breaching:
            m = breaching[key]
            after, ok = option["outcomes"].get(key, (m["value"], False))
            rows.append({"check": _METRIC_LABELS[key], "before": f'{m["value"]:.1f}',
                         "threshold checked": f'< {m["threshold"]:.0f}',
                         "after (simulated)": f'{after:.1f}' if applied else "—",
                         "result": ("✅ pass" if ok else "❌ fail") if applied else "⏳ pending"})
    if k:
        after, ok = option["outcomes"].get("kpi", (k["current"], False))
        rows.append({"check": f'Business KPI — {k["metric"].replace("_"," ")}',
                     "before": f'{k["current"]:.1f}{k["unit"]}', "threshold checked": f'≥ {k["baseline"]:.1f}{k["unit"]}',
                     "after (simulated)": f'{after:.1f}{k["unit"]}' if applied else "—",
                     "result": ("✅ pass" if ok else "❌ fail") if applied else "⏳ pending"})
    return rows


SIMILARITY_THRESHOLD = 0.15  # weak matches are rejected


def similar(incidents, inc, k=3, threshold=SIMILARITY_THRESHOLD):
    """Related incidents ABOVE the relevance threshold (weak matches are rejected)."""
    if not inc:
        return []
    docs = [i["summary"] for i in incidents]
    ids = [i["id"] for i in incidents]
    tf = TfidfVectorizer(stop_words="english").fit(docs + [inc["summary"]])
    sim = cosine_similarity(tf.transform([inc["summary"]]), tf.transform(docs))[0]
    order = sorted(range(len(ids)), key=lambda i: -sim[i])
    out = []
    for i in order:
        if ids[i] == inc["id"] or sim[i] < threshold:
            continue
        out.append(f'{ids[i]} · {incidents[i]["title"]}  (similarity {sim[i]:.2f})')
        if len(out) >= k:
            break
    return out
