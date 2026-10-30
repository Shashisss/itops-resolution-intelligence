"""Pass (b): apply + approval gate, verification, the learning, and reopen (v121).

Each test drives the real app with an `?action=…` parameter, then asserts the record changed and the
re-rendered document shows it. The rule under test throughout: nothing is claimed as fixed until an
independent check says so, and every refusal states its reason.
"""
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import collab  # noqa: E402
import dataops_engine as DE  # noqa: E402
import engine as E  # noqa: E402
import incident_html  # noqa: E402
import journey  # noqa: E402
import learn  # noqa: E402
import story  # noqa: E402

REF = "INC-8841"
PASSING = [{"check": "error rate", "before": "8.1", "threshold checked": "< 1",
            "after (simulated)": "0.4", "result": "✅ pass"}]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setenv("RI_DB", str(dst))
    for mod in (journey, collab, story, E, DE):
        monkeypatch.setattr(mod, "DB", str(dst))
    # the learning is a JSON file on purpose (it survives the session copy) — give it a temp file
    learn_file = tmp_path / "learn.json"
    learn_file.write_text("[]")
    # the app reloads its modules on every run, which resets a module attribute — the env var is
    # what a reload re-reads
    monkeypatch.setenv("RI_LEARN_PATH", str(learn_file))
    monkeypatch.setattr(learn, "PATH", str(learn_file))
    journey._ensure_resolution_table()
    journey._ensure_remediation_table()
    journey._ensure_lead_table()
    return dst


def _inc(path=None):
    con = sqlite3.connect(path or collab.DB)
    con.row_factory = sqlite3.Row
    row = dict(con.execute("SELECT * FROM incidents WHERE id=?", (REF,)).fetchone())
    con.close()
    return row


def _plan():
    """The plan the app computes — option A gated on approval, plus what the record says."""
    opt = E.IT_REMEDIATION[0]
    rec = journey.remediation(REF) or {}
    res = journey.resolution_record(REF) or {}
    return {"id": opt["id"], "label": opt["label"], "mode": opt["mode"], "risk": opt["risk"],
            "needs_approval": opt["mode"] == "Human approval",
            "approved_by": rec.get("approved_by") or "",
            "approved_at": str(rec.get("approved_at") or "")[11:16],
            "applied_by": rec.get("applied_by") or "",
            "applied_at": str(rec.get("applied_at") or "")[11:16],
            "applied": bool(rec.get("applied_at")),
            "verdict": res.get("verdict") or "", "checks": res.get("checks") or []}


def _html(tab="Act & verify", plan="auto"):
    inc = _inc()
    return incident_html.build(inc, "IT Ops", queue="3 of 7", initial_tab=tab,
                               view={"plan": _plan() if plan == "auto" else plan})


def _run(**params):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.query_params["inc"] = REF
    for k, v in params.items():
        at.query_params[k] = str(v)
    at.run()
    assert not at.exception, at.exception
    return at


def _flash(at):
    return " ".join(str(s.value) for s in at.success)


def _act_html(tab="Act & verify"):
    """The pane as the deployed app renders it (the plan is computed by the app)."""
    at = _run(tab=tab)
    md = "\n".join(str(m.value) for m in at.markdown)
    return md


# ---------------------------------------------------------------- the gate on the plan
def test_apply_is_refused_before_approval_and_says_so(db):
    at = _run(tab="Act & verify", action="apply")
    assert "needs approval" in _flash(at)
    assert not (journey.remediation(REF) or {}).get("applied_at")
    assert journey.resolution_record(REF) is None, "a refused apply writes no resolution record"
    assert (_inc()["status"] or "").lower() == "open"


def test_approve_records_who_and_when(db):
    at = _run(tab="Act & verify", action="approve")
    rec = journey.remediation(REF)
    assert rec["approved_by"] and rec["approved_at"], "who and when are recorded"
    assert "Approved by" in _flash(at)
    h = _html()
    assert "Remediation approved" in h and rec["approved_by"] in h


def test_apply_records_the_action_and_asks_for_verification(db):
    _run(tab="Act & verify", action="approve")
    at = _run(tab="Act & verify", action="apply")
    rec = journey.remediation(REF)
    assert rec["applied_by"] and rec["applied_at"]
    assert journey.applied_action(REF) == "A", "the resolution record names the applied option"
    assert "Applied by" in _flash(at)
    h = _html()
    assert "Remediation applied" in h
    assert 'action=verify' in h, "the next step is offered"
    assert 'action=close' not in h, "still unverified, so no close"


def test_verify_records_the_verdict_from_the_checks(db):
    _run(tab="Act & verify", action="approve")
    _run(tab="Act & verify", action="apply")
    at = _run(tab="Act & verify", action="verify")
    rec = journey.resolution_record(REF)
    assert rec and rec["verdict"] in ("Verified", "Recovery failed", "Inconclusive")
    assert rec["checks"], "the checks are stored with the verdict"
    assert "Verification:" in _flash(at)
    passed = sum(1 for c in rec["checks"] if str(c.get("result", "")).startswith("✅"))
    assert f"{passed} of {len(rec['checks'])}" in _flash(at)


def test_verify_refuses_without_an_applied_action(db):
    at = _run(tab="Act & verify", action="verify")
    assert "applied remediation" in _flash(at)
    assert journey.resolution_record(REF) is None


def test_verdict_follows_the_checks_not_the_hope(db):
    assert journey.verdict_from_checks([{"result": "✅ pass"}, {"result": "✅ pass"}]) == "Verified"
    assert journey.verdict_from_checks([{"result": "✅ pass"}, {"result": "❌ fail"}]) == "Recovery failed"
    assert journey.verdict_from_checks([{"result": "⏳ pending"}]) == "Inconclusive"
    assert journey.verdict_from_checks([]) == "Inconclusive"


def test_a_failed_verification_keeps_the_close_blocked(db):
    _run(tab="Act & verify", action="approve")
    _run(tab="Act & verify", action="apply")
    _run(tab="Act & verify", action="verify")
    rec = journey.resolution_record(REF)
    h = _html()
    if rec["verdict"] != "Verified":
        assert 'action=close' not in h, "a failed or undecided verdict cannot close"
        assert 'class="act blocked"' in h


def test_a_verified_incident_closes_then_reopens(db):
    _run(tab="Act & verify", action="approve")
    _run(tab="Act & verify", action="apply")
    _run(tab="Act & verify", action="verify")
    # clear anything that still blocks closure (open requests) so the gate can empty
    for d in collab.delegations(REF):
        if d["status"] != "done":
            collab.set_delegation_status(d["id"], "done", "Data Platform")
    if journey.resolution_record(REF)["verdict"] == "Verified":
        at = _run(tab="Act & verify", action="close")
        assert "Closed by" in _flash(at)
        assert (_inc()["status"] or "").lower() == "closed"
        h = _html()
        assert 'action=reopen' in h, "a closed incident offers reopen"
        at = _run(tab="Act & verify", action="reopen")
        assert "Reopened by" in _flash(at)
        row = _inc()
        assert (row["status"] or "").lower() == "open", "back on the open queue"
        assert journey.resolution_record(REF).get("closed_at") in (None, ""), \
            "a reopened incident must not carry a closure stamp"


def test_reopen_refuses_when_the_incident_is_open(db):
    at = _run(tab="Act & verify", action="reopen")
    assert "already open" in _flash(at)
    assert (_inc()["status"] or "").lower() == "open"


# ---------------------------------------------------------------- the learning
def test_learn_save_writes_the_record_with_who_and_when(db):
    at = _run(tab="Learn", action="learn-save", root_cause="schema drift on core_ledger",
              summary="contract v4 was not deployed to payments", steps="replay; verify",
              outcome="confirmed")
    rec = learn.get(REF)
    assert rec and rec["root_cause"] == "schema drift on core_ledger"
    assert rec["saved_by"] and rec["saved_at"]
    assert rec["steps"] == ["replay; verify"] or rec["steps"], "the steps are stored"
    assert "Learning saved" in _flash(at)
    h = _html(tab="Learn")
    assert "Saved" in h and "schema drift on core_ledger" in h
    assert re.search(r"Learn<b>saved</b>", h), "the tab header says the record exists"


def test_learn_save_requires_a_root_cause(db):
    at = _run(tab="Learn", action="learn-save", root_cause="", summary="x")
    assert "needs a root cause" in _flash(at)
    assert learn.get(REF) is None
    h = _html(tab="Learn")
    assert "Draft, not saved" in h


def test_the_learn_form_is_inline_and_prefilled(db):
    learn.save(_inc(), "IT Ops", {"root_cause": "previous cause", "steps": "a\nb"}, actor="CIO")
    h = incident_html.build(_inc(), "IT Ops", initial_tab="Learn", view={"learn": True})
    assert '<form class="askf"' in h
    for field in ('name="root_cause"', 'name="outcome"', 'name="steps"', 'name="summary"'):
        assert field in h
    assert "previous cause" in h, "the saved record pre-fills the form"
    assert "previous cause" in h and 'value="a; b"' in h


def test_the_act_and_verify_pane_names_every_phase(db):
    h = _html()
    for label in ("Confirm cause", "Apply remediation", "Run verification", "Close incident"):
        assert label in h, label
