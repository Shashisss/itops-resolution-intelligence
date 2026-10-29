"""The graph store — nodes, edges, provenance, and the migration off the flat tables.

The product's claim is that the incident record is a graph. These tests hold the store to that
claim: every incident is a node, every connection carries a source, a confidence and whether it was
observed or inferred, and an older database gains the graph without losing a row.
"""
import os
import pathlib
import shutil
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import graph  # noqa: E402
import journey  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setattr(graph, "DB", str(dst))
    monkeypatch.setattr(journey, "DB", str(dst))
    graph.project(str(dst))
    return dst


def test_every_incident_and_every_dop_incident_is_a_node(db):
    con = sqlite3.connect(db)
    refs = [r[0] for r in con.execute("SELECT id FROM incidents")]
    refs += [r[0] for r in con.execute("SELECT id FROM dop_incidents")]
    con.close()
    g = graph.GraphStore(str(db))
    for ref in refs:
        node = g.node(graph.incident_node_id(ref))
        assert node, f"{ref} has no node"
        assert node["type"] == "Incident"
    assert len(refs) == 7


def test_the_node_and_edge_vocabulary_is_closed(db):
    g = graph.GraphStore(str(db))
    types = {n["type"] for n in g.nodes()}
    assert types <= set(graph.NODE_TYPES), types - set(graph.NODE_TYPES)
    con = sqlite3.connect(db)
    etypes = {r[0] for r in con.execute("SELECT DISTINCT type FROM graph_edges")}
    bases = {r[0] for r in con.execute("SELECT DISTINCT basis FROM graph_edges")}
    con.close()
    assert etypes <= set(graph.EDGE_TYPES), etypes - set(graph.EDGE_TYPES)
    assert bases <= {"observed", "inferred"}


def test_every_edge_carries_source_confidence_and_basis(db):
    g = graph.GraphStore(str(db))
    rows = g.neighbours("inc:INC-8841")
    assert rows
    for row in rows:
        edge = row["edge"]
        assert edge["source"], f'{edge["id"]} has no source'
        assert edge["confidence"] is not None and 0.0 <= edge["confidence"] <= 1.0
        assert edge["basis"] in ("observed", "inferred")


def test_neighbours_group_by_edge_type_and_keep_direction(db):
    g = graph.GraphStore(str(db))
    rows = g.neighbours("inc:INC-8841")
    by_type = {}
    for r in rows:
        by_type.setdefault(r["edge"]["type"], []).append(r)
    # the story needs all of these on the incident screen
    for etype in ("caused_by", "evidenced_by", "affects", "observed_in", "resolved_by"):
        assert etype in by_type, f"{etype} missing from the incident's connections"
    assert all(r["direction"] == "out" for r in by_type["evidenced_by"])
    filtered = g.neighbours("inc:INC-8841", edge_type="evidenced_by")
    assert {r["edge"]["type"] for r in filtered} == {"evidenced_by"}
    assert len(filtered) == len(by_type["evidenced_by"])


def test_observed_and_inferred_are_distinguishable_on_the_same_incident(db):
    g = graph.GraphStore(str(db))
    rows = g.neighbours("inc:INC-8841")
    observed = [r for r in rows if r["edge"]["basis"] == "observed"]
    inferred = [r for r in rows if r["edge"]["basis"] == "inferred"]
    assert observed and inferred, "the panel needs both kinds to be honest"
    # the DB saturation signal is the classic competing, low-confidence hypothesis
    db_signal = [r for r in rows if r["node"]["business_key"] == "M3"]
    assert db_signal, "the DB connection signal should be attached to the incident"
    edge = db_signal[0]["edge"]
    assert edge["basis"] == "inferred" and edge["confidence"] <= 0.35
    assert "active_connections" in edge["source"]


def test_path_finds_the_cross_domain_route(db):
    g = graph.GraphStore(str(db))
    route = g.path("inc:INC-8841", "inc:DOP-1001")
    assert route, "the IT incident must be reachable from the DataOps failure"
    assert route[0] == "inc:INC-8841" and route[-1] == "inc:DOP-1001"
    # and the stale-data signal is on a route to the schema change that started it
    assert g.path("inc:INC-8841", "chg:T-1")
    assert g.path("inc:INC-8841", "inc:INC-8841") == ["inc:INC-8841"]
    assert g.path("inc:INC-8841", "inc:NOT-A-NODE") is None


def test_traverse_expands_by_level_and_stops_at_depth(db):
    g = graph.GraphStore(str(db))
    two = g.traverse("inc:INC-8841", 2)
    assert two["levels"][0]["nodes"][0]["id"] == "inc:INC-8841"
    assert len(two["levels"]) == 3
    assert two["reached"] == len({n["id"] for lvl in two["levels"] for n in lvl["nodes"]}) - 1
    one = g.traverse("inc:INC-8841", 1)
    assert one["reached"] < two["reached"], "depth must bound the expansion"
    assert all(e["type"] in graph.EDGE_TYPES for lvl in two["levels"] for e in lvl["edges"])


def test_an_older_database_gains_the_graph_without_losing_data(db):
    """The migration: drop the graph, keep the incidents, re-project."""
    con = sqlite3.connect(db)
    before = con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    before_dop = con.execute("SELECT COUNT(*) FROM dop_incidents").fetchone()[0]
    comments = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    con.executescript("DROP TABLE graph_edges; DROP TABLE graph_nodes;")
    con.commit()
    con.close()

    result = graph.ensure(str(db))
    assert result.get("nodes"), result
    g = graph.GraphStore(str(db))
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == before
    assert con.execute("SELECT COUNT(*) FROM dop_incidents").fetchone()[0] == before_dop
    assert con.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == comments
    con.close()
    assert g.node("inc:INC-8841")
    assert g.neighbours("inc:INC-8841")
    # idempotent: a second call does not duplicate edges
    edges = len(g.neighbours("inc:INC-8841"))
    graph.project(str(db))
    assert len(g.neighbours("inc:INC-8841")) == edges


def test_the_connections_panel_renders_on_the_incident_screen():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.query_params["inc"] = "INC-8841"
    at.query_params["expand"] = "connections"   # v106 deep link: the section opens for the URL
    at.run()
    assert not at.exception, at.exception
    text = " ".join(str(x.value) for x in at.markdown)
    text += " " + " ".join(str(b.label) for b in at.button)
    assert "Connections" in text
    assert "Caused by" in text and "Evidenced by" in text
    assert "observed" in text and "inferred" in text
    assert "source" in text, "every row shows where the claim came from"
