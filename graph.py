#!/usr/bin/env python3
"""Graph store — the incident record as nodes and edges behind one interface.

The demo still writes its actions into the relational tables (a per-session copy of ``ops.db``), but
the shape the views read is a property graph: nodes typed Incident, Signal, Change, Service, KPI,
Runbook, Learn, Team, Policy, and edges typed caused_by, observed_in, affects, resolved_by,
evidenced_by, learned_from, depends_on.

Every edge carries its own provenance — the ``source`` it came from, a ``confidence`` in 0..1, and
``basis`` = observed | inferred — because "the pipeline failure left the data stale" and "the DB
signal might be contributing" must not look the same on screen. The basis belongs to the edge, not to
the node: a metric is an observed fact, while the claim that it caused the incident is inferred.

``GraphStore`` is the only thing the UI calls: ``neighbours()``, ``path()``, ``traverse()``. Moving to
Neo4j later means reimplementing those (plus the upserts) — the views stay as they are.

``project()`` is the migration: it reads the relational tables that already exist and upserts the
graph, so a database created by an earlier build gains the graph without losing a row. Legacy free
text in ``thread_edges`` is mapped onto node ids once, at import, and keeps its original source and
confidence.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3

DB = os.environ.get("RI_DB", "data/ops.db")
LEARN_PATH = os.environ.get("RI_LEARN_PATH", "data/learn.json")

NODE_TYPES = ("Incident", "Signal", "Change", "Service", "KPI", "Runbook", "Learn", "Team", "Policy")
EDGE_TYPES = ("caused_by", "observed_in", "affects", "resolved_by", "evidenced_by", "learned_from",
              "depends_on")
BASES = ("observed", "inferred")
_CONF = {"high": 0.9, "medium": 0.6, "low": 0.3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, business_key TEXT NOT NULL,
  properties TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  valid_from TEXT, valid_to TEXT);
CREATE TABLE IF NOT EXISTS graph_edges(
  id TEXT PRIMARY KEY, src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL,
  properties TEXT NOT NULL DEFAULT '{}', source TEXT, confidence REAL, basis TEXT,
  version INTEGER NOT NULL DEFAULT 1, valid_from TEXT, valid_to TEXT);
CREATE INDEX IF NOT EXISTS graph_edges_src ON graph_edges(src);
CREATE INDEX IF NOT EXISTS graph_edges_dst ON graph_edges(dst);
CREATE INDEX IF NOT EXISTS graph_nodes_type ON graph_nodes(type);
"""


def _json(text, default=None):
    try:
        return json.loads(text) if text else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _node(row):
    return {"id": row["id"], "type": row["type"], "business_key": row["business_key"],
            "properties": _json(row["properties"]), "version": row["version"],
            "valid_from": row["valid_from"], "valid_to": row["valid_to"]}


def incident_node_id(ref):
    return f"inc:{ref}"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


# ================================================================= the store
class GraphStore:
    """Node/edge access over SQL. The interface a Neo4j projection would also implement."""

    def __init__(self, db=None):
        self.db = db or DB

    # ---------------------------------------------------------------- plumbing
    def _con(self):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        return con

    def available(self):
        try:
            con = self._con()
            con.execute("SELECT 1 FROM graph_nodes LIMIT 1").fetchall()
            con.close()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- nodes
    def node(self, node_id):
        con = self._con()
        r = con.execute("SELECT * FROM graph_nodes WHERE id=?", (node_id,)).fetchone()
        con.close()
        return _node(r) if r else None

    def nodes(self, type=None, limit=None):
        con = self._con()
        sql = "SELECT * FROM graph_nodes" + (" WHERE type=?" if type else "") + " ORDER BY type, business_key"
        rows = con.execute(sql, (type,) if type else ()).fetchall()
        con.close()
        return [_node(r) for r in rows[:limit] if limit] if limit else [_node(r) for r in rows]

    def counts(self):
        con = self._con()
        by_type = {r["type"]: r["n"] for r in con.execute(
            "SELECT type, COUNT(*) AS n FROM graph_nodes GROUP BY type")}
        by_basis = {r["basis"]: r["n"] for r in con.execute(
            "SELECT basis, COUNT(*) AS n FROM graph_edges GROUP BY basis")}
        con.close()
        return {"nodes": sum(by_type.values()), "edges": sum(by_basis.values()),
                "node_types": by_type, "edge_basis": by_basis}

    # ---------------------------------------------------------------- the three questions
    def neighbours(self, node_id, edge_type=None, direction="both"):
        """Every connection of a node, optionally filtered to one edge type.

        Returns rows of {"edge": …, "node": <the node at the other end>, "direction": "out"|"in"},
        where direction=out means this node is the edge's subject ("INC-8841 --caused_by--> …")."""
        con = self._con()
        out = []
        if direction in ("out", "both"):
            out += self._neighbours(con, node_id, edge_type, "out")
        if direction in ("in", "both"):
            out += self._neighbours(con, node_id, edge_type, "in")
        con.close()
        order = {t: i for i, t in enumerate(EDGE_TYPES)}
        out.sort(key=lambda r: (order.get(r["edge"]["type"], 99), r["node"]["type"],
                                r["node"]["business_key"]))
        return out

    def _neighbours(self, con, node_id, edge_type, direction):
        here, other = ("e.src", "e.dst") if direction == "out" else ("e.dst", "e.src")
        sql = (f"SELECT e.*, n.id AS n_id, n.type AS n_type, n.business_key AS n_key,"
               f" n.properties AS n_props, n.version AS n_version, n.valid_from AS n_valid_from,"
               f" n.valid_to AS n_valid_to"
               f" FROM graph_edges e JOIN graph_nodes n ON n.id = {other}"
               f" WHERE {here} = ?" + (" AND e.type = ?" if edge_type else ""))
        params = (node_id, edge_type) if edge_type else (node_id,)
        rows = []
        for r in con.execute(sql, params):
            rows.append({
                "direction": direction,
                "edge": {"id": r["id"], "src": r["src"], "dst": r["dst"], "type": r["type"],
                         "properties": _json(r["properties"]), "source": r["source"],
                         "confidence": r["confidence"], "basis": r["basis"], "version": r["version"]},
                "node": {"id": r["n_id"], "type": r["n_type"], "business_key": r["n_key"],
                         "properties": _json(r["n_props"]), "version": r["n_version"],
                         "valid_from": r["n_valid_from"], "valid_to": r["n_valid_to"]},
            })
        return rows

    def path(self, src, dst, max_depth=6, directed=False):
        """Shortest path between two nodes as a node-id list, or None.

        Undirected by default: "how are these two connected" is the question the screen asks. The
        hop that connects the payment incident to the failed pipeline runs backwards through the
        stale-data signal, and refusing to walk that way would hide the story."""
        if src == dst:
            return [src]
        if directed:
            step = "SELECT e.src AS a, e.dst AS b FROM graph_edges e"
        else:
            step = ("SELECT e.src AS a, e.dst AS b FROM graph_edges e "
                    "UNION ALL SELECT e.dst AS a, e.src AS b FROM graph_edges e")
        sql = f"""
        WITH RECURSIVE walk(node, depth, trail) AS (
            SELECT ?, 0, ?
            UNION ALL
            SELECT e.b, walk.depth + 1, walk.trail || '|' || e.b
            FROM walk JOIN ({step}) e ON e.a = walk.node
            WHERE walk.depth < ? AND instr('|' || walk.trail || '|', '|' || e.b || '|') = 0
        )
        SELECT trail FROM walk WHERE node = ? ORDER BY depth LIMIT 1
        """
        con = self._con()
        row = con.execute(sql, (src, src, max_depth, dst)).fetchone()
        con.close()
        return row["trail"].split("|") if row else None

    def traverse(self, start, depth=2):
        """Breadth-first expansion up to `depth` hops, returned as levels.

        {"start": node, "levels": [{"depth": 0, "nodes": [...], "edges": [...]}, …], "reached": n}
        Each level lists the edges that first reached its nodes, so a caller can show why a node is
        in the result and with what provenance."""
        root = self.node(start)
        levels = [{"depth": 0, "nodes": [root] if root else [], "edges": []}]
        seen = {start}
        frontier = [start] if root else []
        for d in range(1, max(depth, 0) + 1):
            nodes, edges, nxt = [], [], []
            for nid in frontier:
                for row in self.neighbours(nid):
                    other = row["node"]["id"]
                    if other in seen:
                        continue
                    seen.add(other)
                    nxt.append(other)
                    nodes.append(row["node"])
                    edges.append(row["edge"])
            levels.append({"depth": d, "nodes": nodes, "edges": edges})
            frontier = nxt
            if not frontier:
                break
        return {"start": root, "levels": levels, "reached": len(seen) - 1}

    # ---------------------------------------------------------------- writes
    def upsert_node(self, node_id, node_type, business_key, properties=None, stamp=None):
        if node_type not in NODE_TYPES:
            raise ValueError(f"unknown node type {node_type!r}")
        stamp = stamp or dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        blob = json.dumps(properties or {}, sort_keys=True, default=str)
        con = self._con()
        con.execute(
            "INSERT INTO graph_nodes(id,type,business_key,properties,version,valid_from) "
            "VALUES(?,?,?,?,1,?) "
            "ON CONFLICT(id) DO UPDATE SET type=excluded.type, business_key=excluded.business_key, "
            "properties=excluded.properties, version=graph_nodes.version+1",
            (node_id, node_type, business_key, blob, stamp))
        con.commit()
        con.close()

    def upsert_edge(self, src, dst, edge_type, source, confidence, basis, properties=None, stamp=None):
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"unknown edge type {edge_type!r}")
        if basis not in BASES:
            raise ValueError(f"basis must be one of {BASES}, not {basis!r}")
        stamp = stamp or dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        blob = json.dumps(properties or {}, sort_keys=True, default=str)
        edge_id = f"{src}|{edge_type}|{dst}"
        con = self._con()
        con.execute(
            "INSERT INTO graph_edges(id,src,dst,type,properties,source,confidence,basis,version,valid_from) "
            "VALUES(?,?,?,?,?,?,?,?,1,?) "
            "ON CONFLICT(id) DO UPDATE SET properties=excluded.properties, source=excluded.source, "
            "confidence=excluded.confidence, basis=excluded.basis, version=graph_edges.version+1",
            (edge_id, src, dst, edge_type, blob, source, float(confidence), basis, stamp))
        con.commit()
        con.close()

    def write_many(self, nodes, edges, stamp=None, replace=False):
        """Bulk upsert used by project(): nodes = (id, type, key, props), edges = (src, dst, type,
        props, source, confidence, basis).

        replace=True clears the projection first: a claim the projection no longer makes (a runbook
        that is no longer recommended) must not linger as a stale connection."""
        stamp = stamp or dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        con = self._con()
        if replace:
            con.execute("DELETE FROM graph_edges")
            con.execute("DELETE FROM graph_nodes")
        for nid, ntype, key, props in nodes:
            if ntype not in NODE_TYPES:
                raise ValueError(f"unknown node type {ntype!r} for {nid}")
            con.execute(
                "INSERT INTO graph_nodes(id,type,business_key,properties,version,valid_from) "
                "VALUES(?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET type=excluded.type, "
                "business_key=excluded.business_key, properties=excluded.properties, "
                "version=graph_nodes.version+1",
                (nid, ntype, key, json.dumps(props or {}, sort_keys=True, default=str), stamp))
        for src, dst, etype, props, source, conf, basis in edges:
            if etype not in EDGE_TYPES:
                raise ValueError(f"unknown edge type {etype!r}")
            if basis not in BASES:
                raise ValueError(f"basis must be one of {BASES}, not {basis!r}")
            con.execute(
                "INSERT INTO graph_edges(id,src,dst,type,properties,source,confidence,basis,version,"
                "valid_from) VALUES(?,?,?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET "
                "properties=excluded.properties, source=excluded.source, "
                "confidence=excluded.confidence, basis=excluded.basis, "
                "version=graph_edges.version+1",
                (f"{src}|{etype}|{dst}", src, dst, etype,
                 json.dumps(props or {}, sort_keys=True, default=str), source, float(conf), basis, stamp))
        con.commit()
        con.close()


def store(db=None):
    return GraphStore(db)


# ================================================================= projection / migration
# Free-text labels written into thread_edges by earlier builds, mapped onto node ids once. The
# resolver falls back to matching a node's name, so new rows are not stranded by this table.
LEGACY_ALIASES = {
    "Schema change (core_ledger)": "chg:T-1",
    "Pipeline failure (payments_bronze_ingest)": "inc:DOP-1001",
    "Pipeline failure": "inc:DOP-1001",
    "payments_gold stale": "sig:fresh:ds_pay_gd",
    "Payment API degradation": "inc:INC-8841",
    "DB connection saturation": "sig:metric:M3",
}
# "A → B" in the old thread table read "A led to B"; the graph states the effect first:
# "B --caused_by--> A".
_THREAD_REL = {"caused": "caused_by", "→ stale data": "caused_by", "→ impacts": "caused_by",
               "contributes": "caused_by"}


def _lag_min(ts, now=None):
    try:
        then = dt.datetime.fromisoformat(str(ts))
    except Exception:
        return None
    return int(((now or dt.datetime.now()) - then).total_seconds() / 60)


def _conf_from_ratio(value, threshold):
    if not threshold:
        return 0.5
    ratio = value / threshold
    return 0.9 if ratio >= 1.3 else 0.6 if ratio >= 1.1 else 0.3


def _scope(service_id, svc_edges):
    adj = {}
    for e in svc_edges:
        adj.setdefault(e["src"], []).append(e["dst"])
    seen, stack = {service_id}, [service_id]
    while stack:
        node = stack.pop()
        for child in adj.get(node, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _business_of(service_id, svc_edges):
    for e in svc_edges:
        if e["dst"] == service_id and e["rel"] == "supported_by":
            return e["src"]
    return None


def _recommended_option(inc, opts, metrics, service_id):
    """The policy option whose expected outcome clears every breaching metric on this service."""
    if not opts:
        return None
    breached = {m["metric"] for m in metrics
                if m.get("service_id") == service_id and m["value"] > m["threshold"]}
    for opt in opts:
        outcomes = opt.get("outcomes") or {}
        if breached and all(outcomes[k][1] for k in breached if k in outcomes):
            return opt
    return opts[0]


def _remediation():
    out = {"IT Ops": [], "DataOps": []}
    try:
        import engine
        out["IT Ops"] = list(getattr(engine, "IT_REMEDIATION", []))
    except Exception:
        pass
    try:
        import dataops_engine
        out["DataOps"] = list(getattr(dataops_engine, "DOP_REMEDIATION", []))
    except Exception:
        pass
    return out


def _learn_records():
    try:
        with open(LEARN_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def project(db=None, now=None):
    """Upsert the graph from the relational tables. Idempotent — safe on every start, and the way an
    existing database (one built before this store existed) gains the graph without losing data."""
    g = GraphStore(db)
    con = sqlite3.connect(g.db)
    con.row_factory = sqlite3.Row
    rows = lambda sql: [dict(r) for r in con.execute(sql)]  # noqa: E731
    services = rows("SELECT * FROM services")
    datasets = rows("SELECT * FROM dop_datasets")
    pipelines = rows("SELECT * FROM pipelines")
    svc_edges = rows("SELECT * FROM edges")
    lineage = rows("SELECT * FROM dop_lineage")
    pio = rows("SELECT * FROM pipeline_io")
    sdata = rows("SELECT * FROM service_data")
    changes = rows("SELECT * FROM changes")
    metrics = rows("SELECT * FROM metrics")
    kpis = rows("SELECT * FROM kpis")
    runs = rows("SELECT * FROM dop_runs")
    fresh = rows("SELECT * FROM dop_freshness")
    timeline = rows("SELECT * FROM timeline")
    correlations = rows("SELECT * FROM correlations")
    tickets = rows("SELECT * FROM tickets")
    teams = rows("SELECT * FROM olas")
    incidents = rows("SELECT * FROM incidents")
    dop_incidents = rows("SELECT * FROM dop_incidents")
    thread = rows("SELECT * FROM thread_edges")
    con.close()

    nodes, edges = [], []

    def N(nid, ntype, key, **props):
        nodes.append((nid, ntype, key, props))

    def E(src, dst, etype, source, conf, basis, **props):
        edges.append((src, dst, etype, props, source, float(conf), basis))

    # ---- services, datasets, pipelines ------------------------------------------------
    for s in services:
        N(f'svc:{s["id"]}', "Service", s["id"], name=s["name"], kind=s["type"], owner=s.get("owner"))
    for d in datasets:
        N(f'ds:{d["id"]}', "Service", d["id"], name=d["name"], kind="dataset", layer=d["layer"],
          owner=d.get("owner_team"))
    for p in pipelines:
        N(f'pipe:{p["id"]}', "Service", p["id"], name=p["name"], kind="pipeline",
          owner=p.get("owner_team"), criticality=p.get("criticality"),
          freshness_sla_min=p.get("freshness_sla_min"))
    for e in svc_edges:
        E(f'svc:{e["src"]}', f'svc:{e["dst"]}', "depends_on", f'Dependency map · {e["rel"]}', 0.95,
          "observed", rel=e["rel"])
    for l in lineage:
        E(f'ds:{l["src"]}', f'ds:{l["dst"]}', "depends_on", "Lineage · dop_lineage", 0.95, "observed")
    for p in pio:
        if p["direction"] == "reads":
            E(f'pipe:{p["pipeline_id"]}', f'ds:{p["dataset_id"]}', "depends_on",
              "Pipeline IO · reads", 0.9, "observed")
        else:
            E(f'ds:{p["dataset_id"]}', f'pipe:{p["pipeline_id"]}', "depends_on",
              "Pipeline IO · produces", 0.9, "observed")
    for link in sdata:
        E(f'svc:{link["service_id"]}', f'ds:{link["dataset_id"]}', "depends_on",
          "Service → dataset link", 0.9, "observed")

    # ---- changes ---------------------------------------------------------------------
    for ch in changes:
        N(f'chg:{ch["id"]}', "Change", ch["id"], description=ch["description"],
          deployed_at=ch["deployed_at"], owner=ch.get("owner"))
        E(f'chg:{ch["id"]}', f'svc:{ch["service_id"]}', "affects",
          f'Change record {ch["id"]}', 0.95, "observed")
    for ev in timeline:
        if ev["kind"] != "change":
            continue
        N(f'chg:{ev["id"]}', "Change", ev["id"], detail=ev["detail"], at=ev["ts"],
          domain="DataOps" if ev["domain"] == "dataops" else "IT Ops")

    # ---- signals: telemetry, failed runs, freshness ----------------------------------
    # data_age_min has ONE definition (journey.freshness, now − last_updated). The stored metric row
    # freezes the number at seed time, so the graph takes the live value here — otherwise the panel
    # would contradict the Investigation section two sections above it.
    lag_by_ds = {f["dataset_id"]: _lag_min(f["last_updated"], now) for f in fresh}
    ds_by_service = {link["service_id"]: link["dataset_id"] for link in sdata}
    live_value = {}
    for m in metrics:
        value = m["value"]
        if m["metric"] == "data_age_min":
            live = lag_by_ds.get(ds_by_service.get(m["service_id"]))
            if live is not None:
                value = float(live)
        live_value[m["id"]] = value
    for m in metrics:
        value = live_value[m["id"]]
        ratio = (value / m["threshold"]) if m["threshold"] else 0
        N(f'sig:metric:{m["id"]}', "Signal", m["id"], metric=m["metric"], value=value,
          threshold=m["threshold"], service=m["service_id"], breaching=value > m["threshold"],
          ratio=round(ratio, 2))
        E(f'sig:metric:{m["id"]}', f'svc:{m["service_id"]}', "observed_in",
          f'Telemetry · {m["metric"]} {value:g} vs {m["threshold"]:g}', 0.95, "observed")
    for f in fresh:
        lag = _lag_min(f["last_updated"], now)
        if lag is None or lag <= f["sla_min"]:
            continue
        name = next((d["name"] for d in datasets if d["id"] == f["dataset_id"]), f["dataset_id"])
        N(f'sig:fresh:{f["dataset_id"]}', "Signal", f'freshness:{f["dataset_id"]}', lag_min=lag,
          sla_min=f["sla_min"], breaching=True, dataset=name)
        E(f'sig:fresh:{f["dataset_id"]}', f'ds:{f["dataset_id"]}', "observed_in",
          f'DataOps · freshness {lag}m > {f["sla_min"]}m SLA', 0.95, "observed")
    for r in runs:
        if r["status"] != "failed":
            continue
        N(f'sig:run:{r["id"]}', "Signal", r["id"], run=r["id"], pipeline=r["pipeline_id"],
          error=r.get("error"), at=r["started_at"])
        E(f'sig:run:{r["id"]}', f'pipe:{r["pipeline_id"]}', "observed_in",
          f'Run {r["id"]} FAILED · {str(r.get("error") or "")[:56]}', 0.95, "observed")

    # ---- KPIs, runbooks, policies, teams ---------------------------------------------
    for k in kpis:
        N(f'kpi:{k["id"]}', "KPI", k["id"], metric=k["metric"], unit=k["unit"],
          baseline=k["baseline"], current=k["current"], business_service=k["business_service"])
    options = _remediation()
    for domain, opts in options.items():
        prefix = "it" if domain == "IT Ops" else "dop"
        for opt in opts:
            N(f'rb:{prefix}:{opt["id"]}', "Runbook", opt["id"], label=opt["label"],
              mode=opt["mode"], risk=opt["risk"], domain=domain)
            pol = f'pol:{slug(opt["mode"])}'
            N(pol, "Policy", opt["mode"], mode=opt["mode"])
            E(f'rb:{prefix}:{opt["id"]}', pol, "depends_on", "policy/policy.rego", 0.95, "observed")
    for t in tickets:
        N(f'rb:ticket:{t["id"]}', "Runbook", t["id"], label=t.get("fix_hint"),
          acceptance=t.get("acceptance"), ticket=t["id"])
    for t in teams:
        N(f'team:{t["team"]}', "Team", t["team"], response_min=t.get("response_min"),
          restore_min=t.get("restore_min"))

    # ---- learn records ---------------------------------------------------------------
    learns = _learn_records()
    for rec in learns:
        ref = rec.get("ref")
        if not ref:
            continue
        N(f'learn:{ref}', "Learn", ref, title=rec.get("title"), signature=rec.get("signature"),
          outcome=rec.get("outcome"), saved_at=rec.get("saved_at"),
          steps=rec.get("steps") or [], root_cause=rec.get("root_cause"))
        E(f'learn:{ref}', f'inc:{ref}', "learned_from",
          f'Learn record saved {rec.get("saved_at")}', 0.95, "observed")

    # ---- incidents -------------------------------------------------------------------
    def incident_edges(inc, domain):
        ref, nid = inc["id"], f'inc:{inc["id"]}'
        service_id = inc.get("service_id")
        dataset_id = inc.get("dataset_id")
        closed = (inc.get("status") or "").lower() == "closed"
        N(nid, "Incident", ref, title=inc.get("title"), priority=inc.get("priority"),
          status=inc.get("status"), domain=domain, stage=inc.get("stage"),
          owner_team=inc.get("owner_team"), confirmed_cause=inc.get("confirmed_cause"))
        if service_id:
            E(nid, f'svc:{service_id}', "observed_in", f'{domain} incident record', 0.95, "observed")
            scope = _scope(service_id, svc_edges)
            for m in metrics:
                value = live_value[m["id"]]
                if m["service_id"] in scope and value > m["threshold"]:
                    E(nid, f'sig:metric:{m["id"]}', "evidenced_by",
                      f'Telemetry · {m["metric"]} {value:g} vs {m["threshold"]:g}',
                      _conf_from_ratio(value, m["threshold"]), "observed",
                      metric=m["metric"])
            for ch in changes:
                if ch["service_id"] == service_id:
                    E(nid, f'chg:{ch["id"]}', "caused_by",
                      f'Change record {ch["id"]} · deployed {ch["deployed_at"]}', 0.7, "inferred")
            biz = _business_of(service_id, svc_edges)
            if biz:
                E(nid, f'svc:{biz}', "affects", f'Business service · {biz}', 0.9, "observed")
                for k in kpis:
                    if k["business_service"] == biz:
                        E(nid, f'kpi:{k["id"]}', "affects",
                          f'KPI · {k["metric"]} {k["current"]:g}{k["unit"]} vs baseline '
                          f'{k["baseline"]:g}{k["unit"]}', 0.9, "observed")
            for link in sdata:
                if link["service_id"] != service_id:
                    continue
                for f in fresh:
                    if f["dataset_id"] != link["dataset_id"]:
                        continue
                    lag = _lag_min(f["last_updated"], now)
                    if lag is None or lag <= f["sla_min"]:
                        continue
                    E(nid, f'sig:fresh:{f["dataset_id"]}', "evidenced_by",
                      f'DataOps · freshness {lag}m > {f["sla_min"]}m SLA', 0.85, "observed")
                    E(nid, f'sig:fresh:{f["dataset_id"]}', "caused_by",
                      f'DataOps · upstream data stale ({f["dataset_id"]}) — engine hypothesis',
                      0.6, "inferred")
        if dataset_id:
            E(nid, f'ds:{dataset_id}', "observed_in", f'{domain} incident record', 0.95, "observed")
            if inc.get("pipeline_id"):
                E(nid, f'pipe:{inc["pipeline_id"]}', "observed_in",
                  "Pipeline failure raised this incident", 0.95, "observed")
            for r in runs:
                if r["pipeline_id"] == inc.get("pipeline_id") and r["status"] == "failed":
                    E(nid, f'sig:run:{r["id"]}', "evidenced_by",
                      f'Run {r["id"]} FAILED · {str(r.get("error") or "")[:48]}', 0.95, "observed")
            for f in fresh:
                if f["dataset_id"] != dataset_id:
                    continue
                lag = _lag_min(f["last_updated"], now)
                if lag is not None and lag > f["sla_min"]:
                    E(nid, f'sig:fresh:{dataset_id}', "evidenced_by",
                      f'DataOps · freshness {lag}m > {f["sla_min"]}m SLA', 0.95, "observed")
            for ch in changes:
                pass
        owner = inc.get("owner_team")
        if owner:
            E(nid, f'team:{owner}', "resolved_by", f'Owning team · {owner}',
              0.9 if closed else 0.8, "observed" if closed else "inferred")
        prefix = "dop" if domain == "DataOps" else "it"
        opt = _recommended_option(inc, options[domain], metrics, service_id)
        if opt:
            # ONE runbook, not the whole library: the policy option whose expected outcome meets the
            # breaching metrics. Listing all three read as "any of these resolved it".
            E(nid, f'rb:{prefix}:{opt["id"]}', "resolved_by",
              f'Recommended action · policy option {opt["id"]} (expected to meet every breaching metric)',
              0.6, "inferred")
        for t in tickets:
            if t.get("incident_id") == ref:
                E(nid, f'rb:ticket:{t["id"]}', "resolved_by",
                  f'Jira {t["id"]} · recorded fix hint', 0.8, "observed")
        comp = service_id or dataset_id
        for rec in learns:
            sig = str(rec.get("signature") or "")
            parts = sig.split("|")
            if rec.get("ref") != ref and len(parts) > 1 and parts[1] == comp:
                E(nid, f'learn:{rec["ref"]}', "learned_from",
                  f'Prior learn record · same component ({sig})', 0.6, "inferred")

    for inc in incidents:
        incident_edges(inc, "IT Ops")
    for inc in dop_incidents:
        incident_edges(inc, "DataOps")

    # a DataOps failure that reaches a customer service is an edge, not a paragraph
    for c in correlations:
        E(f'inc:{c["dop_id"]}', f'inc:{c["it_id"]}', "affects",
          f'Correlation {c["id"]} · {c["shared_cause"]}', 0.85, "observed")

    # ---- legacy thread edges, imported once with their own provenance -----------------
    index = {}
    for nid, ntype, key, props in nodes:
        for label in (props.get("name"), props.get("label"), key, nid):
            if label:
                index.setdefault(str(label).strip().lower(), nid)
        index.setdefault(nid.split(":", 1)[-1].strip().lower(), nid)

    def resolve(label):
        key = str(label or "").strip()
        if key in LEGACY_ALIASES:
            return LEGACY_ALIASES[key]
        hit = index.get(key.lower())
        if hit:
            return hit
        for low, nid in index.items():
            if len(low) > 4 and low in key.lower():
                return nid
        return None

    for te in thread:
        etype = _THREAD_REL.get(str(te.get("rel") or "").strip().lower())
        cause, effect = resolve(te.get("src")), resolve(te.get("dst"))
        if not etype or not cause or not effect:
            continue
        E(effect, cause, etype, te.get("source") or "thread edge",
          _CONF.get(str(te.get("confidence") or "").strip().lower(), 0.5),
          te.get("kind") if te.get("kind") in BASES else "inferred")

    # de-duplicate by id, last writer wins (the imported provenance beats a generic guess)
    uniq_nodes = {}
    for nid, ntype, key, props in nodes:
        uniq_nodes[nid] = (nid, ntype, key, props)
    nodes = list(uniq_nodes.values())
    deduped = {}
    for src, dst, etype, props, source, conf, basis in edges:
        deduped[f"{src}|{etype}|{dst}"] = (src, dst, etype, props, source, conf, basis)
    g.write_many(nodes, list(deduped.values()),
                 now.replace(microsecond=0).isoformat(timespec="seconds") if now else None,
                 replace=True)
    _meta(db, "graph_sig", _thread_sig(db))
    return {"nodes": len(nodes), "edges": len(deduped)}


def _meta(db, key, value=None):
    """Small key/value on the database, used to remember what the projection was built from."""
    con = sqlite3.connect(db or DB)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        if value is None:
            row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row[0] if row else None
        con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE "
                    "SET value=excluded.value", (key, str(value)))
        con.commit()
    finally:
        con.close()
    return value


def _thread_sig(db=None):
    """A fingerprint of the thread links the projection derives edges from.

    Counting rows is not enough and neither is the newest timestamp: editing a link in place keeps
    both and changes the claim. The digest is over the rows themselves, so any edit moves it."""
    con = sqlite3.connect(db or DB)
    try:
        rows = con.execute("SELECT id, thread_ref, src, dst, rel, kind, confidence "
                           "FROM thread_edges ORDER BY id").fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    return hashlib.sha1(repr(rows).encode("utf-8")).hexdigest()


def ensure(db=None):
    """Project if the graph is missing or behind the incidents it should describe."""
    g = GraphStore(db)
    try:
        con = g._con()
        have = con.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
        incidents = 0
        for table in ("incidents", "dop_incidents"):
            try:
                incidents += con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:
                pass
        con.close()
    except Exception:
        return {"nodes": 0, "edges": 0, "skipped": "no database"}
    # Projected already? Only skip if the thread links are the ones this projection was built from:
    # an edited row must reach the graph, and it must replace its edge rather than add a second one.
    sig = _thread_sig(db)
    if have >= incidents > 0 and _meta(db, "graph_sig") == sig:
        return {"nodes": have, "edges": None, "skipped": "already projected"}
    return project(db)
