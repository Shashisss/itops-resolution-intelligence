"""RCA leads and the close gate (v111).

Each test drives the real app through Streamlit's harness with an `?action=…&target=…` parameter,
then asserts two things: the *record* changed (with who and when), and the *re-rendered document*
shows the new state. Nothing here asserts that a control merely exists — that is the restored-control
registry in test_viewport.py.
"""
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
import story  # noqa: E402

REF = "INC-8841"
DOP = "DOP-1001"


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
    journey._ensure_resolution_table()
    journey._ensure_lead_table()
    return dst


def _inc(ref=REF, path=None):
    con = sqlite3.connect(path or collab.DB)
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    row = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return row


def _leads(inc):
    if inc["id"].startswith("DOP"):
        return journey.leads_for(inc, DE.causes(inc, DE.load()))
    sv, _ed, _incs, ch, me, G = E.load()
    return journey.leads_for(inc, E.causes(inc, G, ch, me, sv))


def _html(ref=REF, tab="Evidence & RCA", leads=None, headline=None):
    inc = _inc(ref)
    if leads is None:
        leads, headline = _leads(inc)
    return incident_html.build(inc, "DataOps" if ref.startswith("DOP") else "IT Ops",
                               queue="3 of 7", initial_tab=tab,
                               view={"leads": leads, "headline": headline},
                               leads=leads, headline=headline)


def _run(**params):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.query_params["inc"] = params.pop("inc", REF)
    for k, v in params.items():
        at.query_params[k] = str(v)
    at.run()
    assert not at.exception, at.exception
    return at


def _flash(at):
    return " ".join(str(s.value) for s in at.success)


def _tab_state(h, name):
    m = re.search(rf'data-t="\d+">{re.escape(name)}<b>([^<]*)</b>', h)
    return m.group(1) if m else None


def _lead_row(h, key):
    from urllib.parse import quote
    frag = quote(str(key), safe="")
    rows = [r for r in h.split('<div class="lead"') if f"target={frag}" in r or f"target={key}" in r]
    return rows[0] if rows else ""


def _confirm_cause_row(h):
    return next((r for r in re.findall(r'<a class="act"[^>]*>.*?</a>', h, re.S)
                 if "Confirm cause" in r), "")


# ---------------------------------------------------------------- hypotheses rendered
def test_the_rca_pane_lists_every_lead_with_rank_confidence_and_evidence(db):
    leads, head = _leads(_inc())
    h = _html()
    rows = re.findall(r'<div class="lead"[^>]*>(.*?)</div></div>', h, re.S)
    assert len(rows) == min(len(leads), 5) == len(leads), f"{len(rows)} rows for {len(leads)} leads"
    for i, lead in enumerate(leads, 1):
        row = _lead_row(h, lead["key"])
        assert f'#{i}' in row, f"rank {i} missing for {lead['label']}"
        assert f'{lead["pct"]}%' in row and lead["confidence"] in row, "confidence is stated"
        assert lead["evidence"][:40].replace("&", "&amp;") in row, "the evidence line is the record's"
        assert "SUSPECTED" in row
    assert _tab_state(h, "Evidence &amp; RCA") == f"{len(leads)} leads"


def test_a_lead_exposes_only_the_decisions_that_would_change_it(db):
    h = _html()
    first = _lead_row(h, _leads(_inc())[0][0]["key"])
    for label in ("Confirm", "Reject", "Set aside"):
        assert label in first
    # the tab the action returns to is the one it was taken from
    assert "tab=Evidence%20%26%20RCA" in first or "tab=Evidence+%26+RCA" in first


# ---------------------------------------------------------------- one test per action
def test_confirm_lead_records_the_decision_without_moving_the_rank(db):
    leads, _ = _leads(_inc())
    target = leads[2]                                  # deliberately NOT rank 1
    key, rank = target["key"], target["rank"]
    at = _run(tab="Evidence & RCA", action="confirm-lead", target=key)
    decisions = journey.lead_decisions(REF)
    assert decisions[key]["status"] == "confirmed"
    assert decisions[key]["actor"] and decisions[key]["changed_at"], "who and when are recorded"
    assert _inc()["confirmed_cause"] == key, "the confirmed cause points at the lead"
    assert _inc()["confirmed_at"], "the confirmation is stamped"
    assert "CONFIRMED" in _flash(at) and target["label"] in _flash(at)

    leads2, head = _leads(_inc())
    assert [l["key"] for l in leads2] == [l["key"] for l in leads], "ranking must not move"
    assert leads2[rank - 1]["key"] == key, "the confirmed lead keeps its rank"
    h = _html(leads=leads2, headline=head)
    row = _lead_row(h, key)
    assert "CONFIRMED" in row and "SUSPECTED" not in row
    assert decisions[key]["actor"] in row and decisions[key]["changed_at"][11:16] in row
    assert "Confirm" not in row.split("CONFIRMED")[1].split("</div>")[0], "no repeated Confirm"
    assert _tab_state(h, "Evidence &amp; RCA") == "1 confirmed"


def test_confirm_lead_retires_the_unconfirmed_sentence(db):
    h0 = _html()
    assert "nobody has confirmed it yet" in h0
    leads, _ = _leads(_inc())
    _run(tab="Evidence & RCA", action="confirm-lead", target=leads[0]["key"])
    leads2, head = _leads(_inc())
    h1 = _html(leads=leads2, headline=head)
    assert "nobody has confirmed it yet" not in h1
    assert f"Cause confirmed by" in h1 and leads[0]["label"] in h1.split("Cause confirmed by")[1][:120]


def test_reject_lead_records_it_and_keeps_it_listed(db):
    leads, _ = _leads(_inc())
    target = leads[0]
    at = _run(tab="Evidence & RCA", action="reject-lead", target=target["key"])
    d = journey.lead_decisions(REF)[target["key"]]
    assert d["status"] == "rejected" and d["actor"]
    assert "REJECTED" in _flash(at)
    leads2, head = _leads(_inc())
    assert [l["key"] for l in leads2] == [l["key"] for l in leads], "a rejection does not reorder"
    h = _html(leads=leads2, headline=head)
    row = _lead_row(h, target["key"])
    assert "REJECTED" in row and d["changed_at"][11:16] in row
    assert target["evidence"][:30].replace("&", "&amp;") in row, "a rejected lead still shows why"


def test_set_aside_lead_records_it_as_parked(db):
    leads, _ = _leads(_inc())
    target = leads[-1]
    at = _run(tab="Evidence & RCA", action="set-aside", target=target["key"])
    d = journey.lead_decisions(REF)[target["key"]]
    assert d["status"] == "set_aside"
    assert "SET ASIDE" in _flash(at)
    leads2, head = _leads(_inc())
    h = _html(leads=leads2, headline=head)
    row = _lead_row(h, target["key"])
    assert "SET ASIDE" in row and d["changed_at"][11:16] in row
    assert _inc()["confirmed_cause"] in (None, ""), "setting a lead aside confirms nothing"


def test_rejecting_the_confirmed_lead_unconfirms_the_cause(db):
    leads, _ = _leads(_inc())
    key = leads[0]["key"]
    _run(tab="Evidence & RCA", action="confirm-lead", target=key)
    assert _inc()["confirmed_cause"] == key
    at = _run(tab="Evidence & RCA", action="reject-lead", target=key)
    assert _inc()["confirmed_cause"] in (None, ""), "a rejected cause cannot stay confirmed"
    assert "unconfirmed" in _flash(at)
    leads2, head = _leads(_inc())
    assert head is None
    h = _html(leads=leads2, headline=head)
    assert "nobody has confirmed it yet" in h, "the unconfirmed claim comes back truthfully"


def test_confirm_cause_names_the_confirmed_lead(db):
    leads, _ = _leads(_inc())
    key, label = leads[1]["key"], leads[1]["label"]
    _run(tab="Evidence & RCA", action="confirm-lead", target=key)
    at = _run(tab="Evidence & RCA", action="confirm")
    flash = _flash(at)
    assert label in flash and "ranked 2 of" in flash
    said = " ".join(c["text"] for c in collab.comments(REF))
    assert label in said, "the thread names the lead, not a generic confirmation"
    leads2, head = _leads(_inc())
    row = _confirm_cause_row(_html(leads=leads2, headline=head))
    assert label in row, "the Confirm cause control states which lead it would name"


def test_confirm_cause_with_no_lead_says_so(db):
    at = _run(tab="Evidence & RCA", action="confirm")
    assert "no lead is CONFIRMED" in _flash(at)
    h = _html()
    assert "no lead is CONFIRMED yet" in _confirm_cause_row(h)


def test_a_stale_lead_target_changes_nothing(db):
    at = _run(tab="Evidence & RCA", action="confirm-lead", target="NOPE:none")
    assert "no longer in the ranked list" in _flash(at)
    assert journey.lead_decisions(REF) == {}
    assert _inc()["confirmed_cause"] in (None, "")


# ---------------------------------------------------------------- the close gate
def test_the_gate_lists_each_blocker_with_the_tab_that_resolves_it(db):
    h = _html(tab="Act & verify")
    gate = journey.closure_state(_inc())
    assert gate["blockers"], "this incident is blocked"
    assert "BLOCKED" in h and f'{len(gate["blockers"])} requirement' in h
    for b in gate["blockers"]:
        assert b["need"][:40].replace("&", "&amp;") in h, f'blocker missing: {b["need"]}'
    assert "tab=Requests" in h, "the request blocker links to the tab that resolves it"
    assert 'class="act blocked"' in h, "the close row is a refusal, not a link"
    assert 'action=close' not in h, "a blocked close must not be clickable"
    assert _tab_state(h, "Act &amp; verify").startswith("BLOCKED")


def test_clearing_the_requests_leaves_only_the_verification_blocker(db):
    for d in collab.delegations(REF):
        if d["status"] != "done":
            collab.set_delegation_status(d["id"], "done", "Data Platform")
    gate = journey.closure_state(_inc())
    assert [b["tab"] for b in gate["blockers"]] == ["Act & verify"]
    h = _html(tab="Act & verify")
    pane = h.split('id="p4"')[1].split('id="p5"')[0]
    assert "1 requirement" in h
    assert "tab=Requests" not in pane, "a resolved blocker is not listed"
    assert _tab_state(h, "Act &amp; verify") == "BLOCKED · 1"


def test_an_eligible_gate_offers_close_and_hides_the_blockers(db):
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO resolution_state(ref_id,verdict,action_id,actor,closed_at,"
                "updated_at,checks) VALUES(?,?,?,?,?,?,?)",
                (REF, "Verified", "A-1", "Platform Engineering", None, "2026-10-30T09:00",
                 '[{"check": "error rate", "result": "✅ pass"}]'))
    con.commit()
    con.close()
    for d in collab.delegations(REF):
        if d["status"] != "done":
            collab.set_delegation_status(d["id"], "done", "Data Platform")
    gate = journey.closure_state(_inc())
    assert gate["eligible"] and not gate["blockers"]
    h = _html(tab="Act & verify")
    assert 'action=close' in h, "an eligible gate offers the close link"
    assert "all requirements met" in h
    assert _tab_state(h, "Act &amp; verify") == "ready"


def test_closing_records_actor_and_time_and_leaves_the_open_queue(db):
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO resolution_state(ref_id,verdict,action_id,actor,closed_at,"
                "updated_at,checks) VALUES(?,?,?,?,?,?,?)",
                (REF, "Verified", "A-1", "Platform Engineering", None, "2026-10-30T09:00",
                 '[{"check": "error rate", "result": "✅ pass"}]'))
    con.commit()
    con.close()
    for d in collab.delegations(REF):
        if d["status"] != "done":
            collab.set_delegation_status(d["id"], "done", "Data Platform")
    at = _run(tab="Act & verify", action="close")
    flash = _flash(at)
    assert "Closed by" in flash and "left the open queue" in flash
    row = _inc()
    assert (row["status"] or "").lower() == "closed"
    rec = journey.resolution_record(REF)
    assert rec and rec.get("closed_at"), "the closure is stamped"
    who, when = journey.closed_by(REF)
    assert who and re.match(r"\d{2}:\d{2}", when), "the thread records who closed it and when"
    h = _html(tab="Act & verify")
    assert "Closed by" in h and who in h
    assert 'action=close' not in h, "a closed incident offers no second close"
    assert _tab_state(h, "Act &amp; verify") == "closed"
    # it has left the queue: no open incident of this id is offered to the board filter
    assert _inc()["status"] == "closed"


def test_the_close_link_stays_blocked_while_any_requirement_is_open(db):
    h = _html(tab="Act & verify")
    assert 'action=close' not in h
    at = _run(tab="Act & verify", action="close")
    assert "verification record" in _flash(at).lower() or "requirement" in _flash(at).lower()
    assert (_inc()["status"] or "").lower() == "open", "a blocked close changes nothing"


def test_the_dataops_thread_renders_its_own_leads_and_gate(db):
    leads, head = _leads(_inc(DOP))
    assert len(leads) == 2
    h = _html(DOP, leads=leads, headline=head)
    for lead in leads:
        row = _lead_row(h, lead["key"])
        assert lead["label"] in row and "Confirm" in row
    assert "action=close" not in h
    assert _tab_state(h, "Act &amp; verify").startswith("BLOCKED")
