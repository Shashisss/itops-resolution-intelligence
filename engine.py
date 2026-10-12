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


def impact_chain(G, node):
    """Upstream path to the business service (for the narrative)."""
    chain, cur, seen = [], node, set()
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        preds = list(G.predecessors(cur))
        cur = preds[0] if preds else None
    return chain


def impacted(G, node):
    """Full impacted subgraph: ancestors (business) + node + descendants (dependencies)."""
    return set(nx.ancestors(G, node)) | {node} | set(nx.descendants(G, node))


def business_service(G, chain, services):
    for n in chain:
        if services[n]["type"] == "business_service":
            return n
    return None


def causes(inc, G, changes, metrics, services):
    """RCA over the impacted subgraph: changes + metric breaches."""
    scope = impacted(G, inc["service_id"])
    out = []
    for ch in changes:
        if ch["service_id"] in scope:
            out.append({"type": "change", "service": ch["service_id"],
                        "owner": ch["owner"] or services[ch["service_id"]]["owner"],
                        "text": f'Recent change on {ch["service_id"]}: {ch["description"]} '
                                f'({ch["deployed_at"]}, {ch["owner"]})'})
    for m in metrics:
        if m["service_id"] in scope and m["value"] > m["threshold"]:
            out.append({"type": "metric", "service": m["service_id"],
                        "owner": services[m["service_id"]]["owner"],
                        "text": f'{m["service_id"]} {m["metric"]} = {m["value"]:.0f} '
                                f'(threshold {m["threshold"]:.0f})'})
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


def similar(incidents, inc, k=3):
    docs = [i["summary"] for i in incidents]
    ids = [i["id"] for i in incidents]
    tf = TfidfVectorizer(stop_words="english").fit(docs + [inc["summary"]])
    sim = cosine_similarity(tf.transform([inc["summary"]]), tf.transform(docs))[0]
    order = sorted(range(len(ids)), key=lambda i: -sim[i])
    out = []
    for i in order:
        if ids[i] == inc["id"]:
            continue
        out.append(f'{ids[i]} · {incidents[i]["title"]}  (similarity {sim[i]:.2f})')
        if len(out) >= k:
            break
    return out
