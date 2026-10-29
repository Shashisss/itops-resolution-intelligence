"""Who's on it — the static agent panel, held to the record it sits on.

Two conditions are non-negotiable: every number in the panel equals the incident record (so the
panel can never contradict the screen beside it), and the panel carries a visible "simulated" chip.
These tests render each defined incident, check the numbers against story/analytics, prove the empty
state for an undefined incident, and prove that a changed record changes the panel.
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import agents  # noqa: E402
import collab  # noqa: E402
import journey  # noqa: E402
import story  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

DEFINED = ["INC-8841", "INC-8850", "INC-8802", "DOP-1001"]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (story, collab, journey):   # agents reads through story's connection
        monkeypatch.setattr(mod, "DB", str(dst))
    return str(dst)


def _inc(db, ref):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    row = con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone()
    con.close()
    return dict(row)


def _panel_markdown(ref):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = ref
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at, "\n".join(m.value for m in at.markdown)


@pytest.mark.parametrize("ref", DEFINED)
def test_each_defined_incident_renders_the_panel(db, ref):
    at, md = _panel_markdown(ref)
    assert '<div class="ri-agents">' in md, f"{ref} must render the panel"
    assert 'class="ri-simchip">SIMULATED' in md, "the simulated chip must be visible on the panel"
    assert "NOT SENT" in md, "the handoff draft must state that it was not sent"
    assert 'class="p on"' in md, "exactly one autonomy rung is highlighted"
    assert md.count('class="p on"') == 1


def test_undefined_incident_shows_a_neutral_empty_state(db):
    at, md = _panel_markdown("DOP-1002")
    assert '<div class="ri-agents">' not in md, "nothing must be invented for an undefined incident"
    assert any("Nothing is defined for this incident" in c.value for c in at.caption)


@pytest.mark.parametrize("ref", DEFINED)
def test_panel_numbers_equal_the_record(db, ref):
    """Wait, SLA, domains, handoffs and the signal weight are the record's own values."""
    inc = _inc(db, ref)
    p = agents.panel(inc)
    assert p is not None
    w, s, c = story.waiting(inc), story.sla(inc), story.cross(inc)
    if w["empty"]:
        assert p["facts"]["wait"] == "—"
    else:
        assert p["facts"]["wait"] == story.fmt_minutes(w["minutes"])
        assert p["facts"]["holder"] == w["who"]
    assert p["facts"]["sla"] == s["text"]
    assert p["facts"]["domains"] == c["domains"]
    assert p["facts"]["handoffs"] == c["handoffs"]
    assert p["handoff"]["stage"] == journey.lifecycle_stage(inc)

    # the signal weight is the recorded basis/confidence, through one mapping
    sig = p["specialist"]["signal"]
    rows = story._rows("SELECT kind, confidence FROM thread_edges WHERE thread_ref=? "
                       "AND kind='inferred' ORDER BY CASE confidence WHEN 'high' THEN 0 "
                       "WHEN 'medium' THEN 1 ELSE 2 END LIMIT 1", (ref,))
    if rows:
        assert sig["score"] == agents.SIGNAL_SCORE["inferred"][rows[0]["confidence"]]
        assert sig["basis"] == "inferred"


def test_inc_8841_shows_the_ledger_signal_at_0_72_inferred(db):
    inc = _inc(db, "INC-8841")
    p = agents.panel(inc)
    assert p["facts"]["wait"] == "53m" or p["facts"]["wait"].endswith("m")
    assert p["specialist"]["signal"]["score"] == 0.72
    assert p["specialist"]["signal"]["basis"] == "inferred"
    assert p["facts"]["domains"] == 3 and p["facts"]["handoffs"] == 2
    assert p["rung"] == "draft"


def test_a_changed_record_changes_the_panel(db):
    """Move the oldest request's clock back 20 minutes: the panel's waiting figure must follow."""
    inc = _inc(db, "INC-8841")
    before = agents.panel(inc)["facts"]["wait"]
    con = sqlite3.connect(db)
    oldest = con.execute("SELECT id, ts FROM delegations WHERE ref_id='INC-8841' "
                         "AND status != 'done' ORDER BY ts LIMIT 1").fetchone()
    ts = dt.datetime.fromisoformat(oldest[1]) + dt.timedelta(minutes=20)
    con.execute("UPDATE delegations SET ts=? WHERE id=?", (ts.isoformat(timespec="seconds"), oldest[0]))
    con.commit()
    con.close()
    after = agents.panel(_inc(db, "INC-8841"))["facts"]["wait"]
    assert after != before, "the panel must not keep a stale number"
    assert after == story.fmt_minutes(story.minutes_between(ts.isoformat(timespec="seconds")))


def test_facts_are_rendered_into_the_panel_text(db):
    """The orchestrator's evidence chips come from the record, not from the JSON."""
    inc = _inc(db, "INC-8841")
    p = agents.panel(inc)
    texts = [f["text"] for f in p["orchestrator"]["facts"]]
    assert any("freshness" in t for t in texts)
    assert any("error rate" in t for t in texts)
    assert any("DOP-1001" in t for t in texts)


def test_only_defined_incidents_have_a_panel(db):
    defined = set(json.loads((ROOT / "agents.json").read_text())["incidents"])
    assert defined == set(DEFINED), "the demo ships four definitions — four, not a generated panel"
    con = sqlite3.connect(db)
    refs = {r[0] for r in con.execute("SELECT id FROM incidents UNION ALL SELECT id FROM dop_incidents")}
    con.close()
    assert refs - defined, "at least one incident is deliberately undefined (the empty state)"


def test_agents_page_lists_six_rows_one_live():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.session_state["nav"] = "Agents"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = "\n".join(m.value for m in at.markdown)
    assert md.count('class="ri-ablock"') == 6
    rows = agents.agents()
    assert len(rows) == 6
    assert sum(1 for r in rows if "live" in r["status"].lower()) == 1
    assert all(r.get("allowed") for r in rows), "every agent states what it may do"
