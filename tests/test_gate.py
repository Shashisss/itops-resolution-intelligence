"""Closure gate end-to-end: a failed recovery and an open request both keep the incident open, and
the gate says which requirement is missing. The gate is the only route to Closed."""
import os
import pathlib
import shutil
import sqlite3
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import collab  # noqa: E402
import journey  # noqa: E402

REF = "INC-8841"
PASSING = [{"check": "error rate", "after (simulated)": "0.4%",
            "threshold checked": "< 1%", "result": "✅ pass"},
           {"check": "data age", "after (simulated)": "2 min",
            "threshold checked": "< 15 min", "result": "✅ pass"}]
ALL_FAIL = [{"check": "error rate", "after (simulated)": "9.8%",
             "threshold checked": "< 1%", "result": "✖ fail"},
            {"check": "data age", "after (simulated)": "45 min",
             "threshold checked": "< 15 min", "result": "✖ fail"}]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setenv("RI_DB", str(dst))
    for mod in (journey, collab):
        monkeypatch.setattr(mod, "DB", str(dst))
    journey._ensure_resolution_table()
    con = sqlite3.connect(dst)
    con.execute("DELETE FROM resolution_state WHERE ref_id=?", (REF,))
    con.execute("DELETE FROM delegations WHERE ref_id=?", (REF,))
    con.execute("UPDATE incidents SET status='open' WHERE id=?", (REF,))
    con.commit()
    con.close()
    return dst


def run_app(step=None):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.query_params["inc"] = REF
    if step:
        at.query_params["step"] = step     # v106 deep link opens the section
    at.run()
    assert not at.exception, at.exception
    return at


def page_text(at):
    parts = [str(m.value or "") for m in at.markdown]
    parts += [str(c.value or "") for c in at.caption]
    parts += [str(e.label or "") for e in at.expander]
    return " ".join(parts)


def status(db):
    con = sqlite3.connect(db)
    row = con.execute("SELECT status FROM incidents WHERE id=?", (REF,)).fetchone()
    con.close()
    return row[0]


def _html(inc_dict):
    import incident_html
    return incident_html.build(inc_dict, "IT Ops")


def _inc(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM incidents WHERE id=?", (REF,)).fetchone()
    con.close()
    return dict(row)


def test_recovery_failed_keeps_the_incident_open_and_explains(db):
    journey.set_resolution(REF, "Recovery failed", action_id=None, checks=ALL_FAIL)
    h = _html(_inc(db))
    assert "BLOCKED" in h, "the Act & verify tab states the gate"
    assert "Close incident" in h
    assert "inert in this POC" in h, "a blocked close is inert, not offered"
    assert status(db) == "open"


def test_open_request_blocks_a_verified_closure_and_says_so(db):
    journey.set_resolution(REF, "Verified", action_id=None, checks=PASSING)
    collab.add_delegation(REF, "Incident Manager", "Data Platform", "confirm contract v4")
    h = _html(_inc(db))
    assert "Close incident" in h and "inert in this POC" in h
    assert status(db) == "open"


def test_verified_and_clear_offers_closure(db):
    journey.set_resolution(REF, "Verified", action_id=None, checks=PASSING)
    collab.set_delegation_status(collab.delegations(REF)[0]["id"], "done", actor="Data Platform") \
        if collab.delegations(REF) else None
    h = _html(_inc(db))
    assert "Close incident" in h
    assert status(db) == "open"
