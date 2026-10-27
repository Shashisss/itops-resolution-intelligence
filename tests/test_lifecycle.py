"""Milestone 1 — lifecycle and recovery integrity.

The rule under test: execution is not closure. A remediation can be applied, but an incident closes
only on an independent verification that passed, with no outstanding request, and closure is idempotent.
"""
import os
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import sqlite3  # noqa: E402

import collab  # noqa: E402
import journey  # noqa: E402

# Real ids from the sample data — closure has to run against incidents that actually exist.
TEST_REFS = ["INC-8841", "INC-8850", "INC-8802", "DOP-1002"]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """A throwaway copy of the demo database so tests never touch the one serving the app."""
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401  (creates it)
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setattr(journey, "DB", str(dst))
    monkeypatch.setattr(collab, "DB", str(dst))
    journey._ensure_resolution_table()
    con = sqlite3.connect(dst)
    for ref in TEST_REFS:
        con.execute("DELETE FROM resolution_state WHERE ref_id=?", (ref,))
        con.execute("DELETE FROM delegations WHERE ref_id=?", (ref,))
        con.execute("UPDATE incidents SET status='open' WHERE id=?", (ref,))
        con.execute("UPDATE dop_incidents SET status='open' WHERE id=?", (ref,))
    con.commit()
    con.close()
    return dst


def incident(ref, status="open"):
    return {"id": ref, "status": status, "created_at": "2026-10-26T10:00", "priority": "P2"}


PASSING = [{"check": "error rate", "result": "✅ pass"}, {"check": "data age", "result": "✅ pass"}]
MIXED = [{"check": "error rate", "result": "✅ pass"}, {"check": "data age", "result": "✖ fail"}]


def test_closure_is_blocked_without_a_verification_record(db):
    state = journey.closure_state(incident("INC-8841"))
    assert state["eligible"] is False
    assert any("verification record" in r for r in state["reasons"])
    ok, msg = journey.close_incident("INC-8841")
    assert ok is False and "verification" in msg.lower()


def test_fix_applied_is_not_a_closure(db):
    journey.set_resolution("INC-8850", "Mitigated", action_id="A1", checks=MIXED)
    state = journey.closure_state(incident("INC-8850"))
    assert state["eligible"] is False
    assert any("Mitigated" in r for r in state["reasons"])


def test_verified_with_open_request_is_still_blocked(db):
    journey.set_resolution("INC-8802", "Verified", action_id="A1", checks=PASSING)
    collab.add_delegation("INC-8802", "CIO", "Data Platform", "confirm rollback", channel="Teams")
    state = journey.closure_state(incident("INC-8802"))
    assert state["eligible"] is False
    assert any("open collaboration request" in r for r in state["reasons"])


def test_verified_and_clear_closes_once(db):
    journey.set_resolution("DOP-1002", "Verified", action_id="A1", checks=PASSING)
    state = journey.closure_state(incident("DOP-1002"))
    assert state["eligible"] is True, state["reasons"]
    ok, msg = journey.close_incident("DOP-1002", actor="Incident Manager")
    assert ok is True, msg
    ok2, msg2 = journey.close_incident("DOP-1002", actor="Incident Manager")
    assert ok2 is False and "already closed" in msg2.lower()


def test_inconclusive_is_not_a_pass(db):
    undecided = [{"check": "error rate", "result": "⏳ source unavailable"},
                 {"check": "data age", "result": "⏳ timed out"}]
    assert journey.verdict(undecided, True) == "Inconclusive"
    journey.set_resolution("INC-8850", "Inconclusive", action_id="A1", checks=undecided)
    state = journey.closure_state(incident("INC-8850"))
    assert state["eligible"] is False
    assert any("Inconclusive" in r for r in state["reasons"])


def test_verdict_mapping_is_explicit():
    assert journey.verdict([], False) == "Investigating"
    assert journey.verdict(PASSING, True) == "Verified"
    assert journey.verdict(MIXED, True) == "Mitigated"
    assert journey.verdict([{"check": "x", "result": "✖ fail"}], True) == "Recovery failed"


def test_execution_is_recorded_once_and_reused_as_the_action_of_record(db):
    journey.set_resolution("INC-8850", "Verified", action_id="ACT-42", checks=PASSING)
    assert journey.applied_action("INC-8850") == "ACT-42"
    rec = journey.resolution_record("INC-8850")
    assert rec["verdict"] == "Verified" and rec["action_id"] == "ACT-42"
    # re-running verification must not invent a second execution
    journey.set_resolution("INC-8850", "Verified", action_id="ACT-42", checks=PASSING)
    assert journey.applied_action("INC-8850") == "ACT-42"


def _row(db, ref):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM incidents WHERE id=?", (ref,)).fetchone()
    con.close()
    return dict(r)


def test_next_action_advances_with_the_evidence(db):
    inc = _row(db, "INC-8850")
    assert journey.next_action(inc)["label"] == "Confirm cause"

    con = sqlite3.connect(db)
    con.execute("UPDATE incidents SET confirmed_cause='schema drift' WHERE id='INC-8850'")
    con.commit()
    con.close()
    inc = _row(db, "INC-8850")
    assert journey.next_action(inc)["label"] == "Bring in owner", "confirming the cause must move the action on"

    collab.add_delegation("INC-8850", "Incident Manager", "Orders Team", "approve backoff fix")
    assert journey.next_action(inc)["label"] == "Execute fix"

    for d in collab.delegations("INC-8850"):
        collab.set_delegation_status(d["id"], "done")
    journey.set_resolution("INC-8850", "Verified", action_id="A", checks=PASSING)
    assert journey.next_action(inc)["label"] == "Close incident"

    ok, _ = journey.close_incident("INC-8850")
    assert ok
    assert journey.next_action(_row(db, "INC-8850"))["label"] is None


def test_next_action_says_verify_after_a_partial_result(db):
    inc = _row(db, "INC-8850")
    con = sqlite3.connect(db)
    con.execute("UPDATE incidents SET confirmed_cause='schema drift' WHERE id='INC-8850'")
    con.commit()
    con.close()
    journey.set_resolution("INC-8850", "Mitigated", action_id="B", checks=MIXED)
    assert journey.next_action(inc)["label"] == "Verify now"
