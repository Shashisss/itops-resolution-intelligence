#!/usr/bin/env python3
"""Resolution-intelligence engine: graph reasoning, RCA, policy, retrieval.
Pure-Python + embedded data — no servers."""
import sqlite3
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
    con.close()
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
    con = sqlite3.connect(DB)
    con.execute("UPDATE incidents SET confirmed_cause=? WHERE id=?", (key, inc_id))
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
            "type": "change", "key": key, "service": ch["service_id"],
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
            "owner": services[m["service_id"]]["owner"],
            "confidence": conf, "status": "confirmed" if confirmed == key else "suspected",
            "evidence": f'{m["metric"]} = {m["value"]:.0f} vs threshold {m["threshold"]:.0f} on {m["service_id"]}',
            "text": f'{m["service_id"]} {m["metric"]} at {m["value"]:.0f} (threshold {m["threshold"]:.0f})',
        })
    return out


def recommend(inc, causes):
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
    {"id": "A", "label": "Roll back CHG-1042 and scale DB connections", "mode": "Human approval",
     "risk": "High (production rollback + DB change)",
     "outcomes": {"p95_latency_ms": (250.0, True), "error_rate_pct": (0.4, True),
                  "active_connections": (600.0, True), "kpi": (98.5, True)}},
    {"id": "B", "label": "Scale DB connections only (no rollback)", "mode": "Policy controlled",
     "risk": "Medium",
     "outcomes": {"p95_latency_ms": (280.0, True), "error_rate_pct": (0.8, True),
                  "active_connections": (620.0, True), "kpi": (94.0, False)}},
    {"id": "C", "label": "Dismiss as transient (no fix)", "mode": "Human approval",
     "risk": "High",
     "outcomes": {"p95_latency_ms": (620.0, False), "error_rate_pct": (7.9, False),
                  "active_connections": (975.0, False), "kpi": (90.0, False)}},
]
_METRIC_LABELS = {"p95_latency_ms": "Latency (p95, ms)", "error_rate_pct": "Error rate (%)",
                  "active_connections": "DB connections"}


def it_verification(inc, ctx, option, applied=True):
    """Independent re-check of raw telemetry against thresholds after a chosen action."""
    G, changes, metrics, services, kpis = ctx["G"], ctx["changes"], ctx["metrics"], ctx["services"], ctx["kpis"]
    scope = impacted(G, inc["service_id"])
    breaching = {m["metric"]: m for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]}
    biz = business_service(G, dependency_paths(G, inc["service_id"])[0], services)
    k = next((x for x in kpis if x["business_service"] == biz), None)
    rows = []
    for key in ["p95_latency_ms", "error_rate_pct", "active_connections"]:
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
