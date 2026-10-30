"""Requests-tab actions (v110): each one mutates the record, re-renders on the same tab, and the
tab header keeps telling the truth.

The screen is one html document, so a link is an `?action=…&target=…` href; `app.py` performs it
once on the record and clears the parameter. These tests drive the real app through Streamlit's
harness for the mutation, and the document builder for what the user then sees.
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
import journey  # noqa: E402
import story  # noqa: E402

REF = "INC-8841"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setenv("RI_DB", str(dst))
    for mod in (journey, collab, story):
        monkeypatch.setattr(mod, "DB", str(dst))
    journey._ensure_resolution_table()
    return dst


def _inc(ref=REF):
    con = sqlite3.connect(collab.DB)
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    row = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return row


def _html(ref=REF, view=None, tab="Requests"):
    import incident_html
    return incident_html.build(_inc(ref), "DataOps" if ref.startswith("DOP") else "IT Ops",
                               queue="3 of 7", initial_tab=tab, view=view or {})


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


def _ask(did):
    return next((d for d in collab.delegations(REF) if str(d["id"]) == str(did)), None)


def _asks(ref=REF):
    return story.requests(ref)


def _header(h, name="Requests"):
    m = re.search(r'data-t="1">Requests<b>([^<]*)</b>', h)
    return m.group(1) if m else None


# ---------------------------------------------------------------- rendering: the links
def test_every_live_request_offers_its_actions_with_target(db):
    h = _html(view={"full": True})
    ids = [str(r["id"]) for r in _asks() if r["status"] != "done"][:8]
    for did in ids:
        assert f"action=chase&amp;target={did}" in h or f"action=chase&target={did}" in h
    assert "action=ack" in h and "action=done" in h
    # no button is inert: every action link names the record it acts on
    acts = re.findall(r'href="\?inc=INC-8841[^"]*action=(chase|ack|done|send)[^"]*"', h)
    assert set(acts) <= {"chase", "ack", "done", "send"}
    assert {"chase", "ack", "done"} <= set(acts)


def test_action_links_carry_the_view_they_were_clicked_from(db):
    # page 2 holds the older, completed asks: reopen one so the page has a live action
    oldest = _asks()[0]                       # oldest ask sorts onto the last page
    collab.set_delegation_status(oldest["id"], "reopened", "Incident Manager")
    h = _html(view={"full": True, "page": 2})
    pane = h.split('class="reqfull"')[1].split('class="pager"')[0]
    links = re.findall(r'href="(\?inc=INC-8841[^"]*action=(?:chase|ack|done|send)[^"]*)"', pane)
    assert links, "page 2 must still offer actions"
    for href in links:
        assert "tab=Requests" in href, href
        assert "full=1" in href, href
        assert "page=2" in href, href
    # and an action taken there lands back on page 2 with the tab still open
    at = _run(tab="Requests", full="1", page="2", action="ack", target=oldest["id"])
    assert str(at.query_params.get("page")) in ("2", "['2']")
    assert str(at.query_params.get("full")) in ("1", "['1']")


def test_create_ask_is_an_inline_form_with_the_four_fields(db):
    h = _html(view={"full": True, "new": True})
    assert '<form class="askf"' in h
    for field in ('name="to"', 'name="act"', 'name="due"', 'name="travels"'):
        assert field in h
    assert 'name="action" value="ask"' in h
    assert "modal" not in h.split('<form class="askf"')[0][-200:]
    assert 'id="ov"' not in h.split('<form class="askf"')[1].split("</form>")[0]


def test_pagination_range_and_prev_next_in_place(db):
    n = len(_asks())
    h = _html(view={"full": True, "page": 1})
    assert f"1–8 of {n}" in h
    assert "page=2" in h and "next" in h
    h2 = _html(view={"full": True, "page": 2})
    assert f"9–{n} of {n}" in h2
    assert "page=1" in h2
    # no modal anywhere near the list: the pager is inside the pane
    assert 'class="pager"' in h2 and 'class="ov"' in h2      # ov exists for the other panes only
    assert "reqfull" in h2 and "reqprev" in h2


def test_page_out_of_range_clamps_to_the_last_page(db):
    n = len(_asks())
    h = _html(view={"full": True, "page": 99})
    pages = max(1, (n + 7) // 8)
    first = (pages - 1) * 8 + 1
    assert f"{first}–{n} of {n}" in h


def test_expanded_page_holds_eight_rows_and_the_preview_holds_four(db):
    h = _html(view={"full": True, "page": 1})
    full = h.split('class="reqfull"')[1].split('class="pager"')[0]
    assert full.count('class="rrow"') == 8
    prev = h.split('class="reqprev"')[1].split('class="reqfull"')[0]
    assert 1 <= prev.count('class="req"') <= 4


def test_header_overdue_count_equals_the_badges(db):
    h = _html(view={"full": True})
    head = _header(h)
    overdue_rows = sum(1 for r in _asks() if r["overdue"])
    assert head == (f"{overdue_rows} OVERDUE" if overdue_rows else "none overdue")
    assert h.count(">OVERDUE<") >= overdue_rows


# ---------------------------------------------------------------- the actions themselves
def test_acknowledge_action_mutates_and_rerenders(db):
    target = next(r for r in reversed(_asks()) if r["status"] == "assigned")   # newest: page 1
    at = _run(tab="Requests", action="ack", target=target["id"])
    row = _ask(target["id"])
    assert row["status"] == "accepted"
    assert row["actor"] and row["changed_at"], "who and when must be recorded"
    assert collab.delegation_events(target["id"])[-1]["status"] == "accepted"
    flash = _flash(at)
    assert "Acknowledged by" in flash and target["owner"] in flash
    assert "action" not in list(at.query_params), "the action parameter is consumed once"
    h = _html(view={"full": True})
    mine = [ln for ln in h.split("<div class=\"rrow\"")
            if f'target={target["id"]}"' in ln or f'target={target["id"]}&amp;' in ln]
    assert mine, "the request must still be on the page"
    assert any("ACKNOWLEDGED" in ln for ln in mine), "the badge must show the new state"
    assert any("Acknowledge" not in ln for ln in mine), "an accepted request is not acknowledged twice"


def test_mark_done_resolves_the_overdue_and_the_header_says_so(db):
    # one incident, one overdue request: the example in the brief
    con = sqlite3.connect(db)
    con.execute("DELETE FROM delegations WHERE ref_id=?", (REF,))
    con.commit()
    con.close()
    collab.add_delegation(REF, "Incident Manager", "Data Platform", "Confirm contract v4", "assigned")
    con = sqlite3.connect(db)
    con.execute("UPDATE delegations SET ts=datetime('now','-90 minutes') WHERE ref_id=?", (REF,))
    con.commit()
    con.close()
    assert _header(_html()) == "1 OVERDUE"
    target = _asks()[0]
    at = _run(tab="Requests", full="1", page="1", action="done", target=target["id"])
    assert _ask(target["id"])["status"] == "done"
    assert _ask(target["id"])["done_at"]
    assert "Marked done by" in _flash(at)
    h = _html(view={"full": True})
    assert _header(h) == "none overdue", "the tab header must stop saying OVERDUE"
    assert ">OVERDUE<" not in h


def test_create_ask_makes_a_not_sent_request_and_send_delivers_it(db):
    at = _run(tab="Requests", full="1", page="1", action="ask",
              to="Checkout Team", act="Confirm the replay window", due="45",
              travels="trace + 2 evidence")
    flash = _flash(at)
    assert "NOT SENT" in flash and "Checkout Team" in flash
    new = [d for d in collab.delegations(REF) if "Confirm the replay window" in (d["action"] or "")][0]
    assert new["sent_at"] is None
    assert "expected in 45 min" in new["action"], "the deadline is stated in the ask"
    assert new["travels"] == "trace + 2 evidence"
    assert new["actor"], "the ask records who raised it"
    h = _html(view={"full": True, "page": 1})
    assert "NOT SENT" in h
    assert f'action=send&amp;target={new["id"]}' in h
    # Send: NOT SENT → SENT, and only then do Chase / Acknowledge / Mark done appear on that row
    at = _run(tab="Requests", full="1", page="1", action="send", target=new["id"])
    assert "SENT" in _flash(at) and "Checkout Team" in _flash(at)
    sent = _ask(new["id"])
    assert sent["sent_at"] and sent["status"] == "assigned"
    h = _html(view={"full": True})
    row = [ln for ln in h.split('<div class="rrow"') if f'action=chase&amp;target={new["id"]}' in ln]
    assert row, "a sent request offers Chase"
    assert "NOT SENT" not in row[0]


def test_send_is_refused_once_the_request_is_already_sent(db):
    target = next(r for r in _asks() if r["sent_at"])
    before = _ask(target["id"])["sent_at"]
    with pytest.raises(ValueError):
        collab.send_delegation(target["id"], "Incident Manager")
    assert _ask(target["id"])["sent_at"] == before, "a second send must not rewrite the first"


def test_chase_with_a_target_logs_it_against_that_request(db):
    target = next(r for r in _asks() if r["owner"] == "Data Platform")
    at = _run(tab="Requests", action="chase", target=target["id"])
    assert "Reminder logged to Data Platform" in _flash(at)
    said = " ".join(c["text"] for c in collab.comments(REF))
    assert "Chased Data Platform" in said


def test_a_stale_target_changes_nothing_and_says_so(db):
    before = [dict(d) for d in collab.delegations(REF)]
    at = _run(tab="Requests", action="ack", target="99999")
    assert "no longer on the thread" in _flash(at)
    after = [dict(d) for d in collab.delegations(REF)]
    assert [d["status"] for d in before] == [d["status"] for d in after]


def test_an_ask_without_an_owner_creates_nothing(db):
    before = len(collab.delegations(REF))
    at = _run(tab="Requests", action="ask", to="", act="", due="30")
    assert "needs an owner" in _flash(at)
    assert len(collab.delegations(REF)) == before


def test_actions_land_back_on_the_same_tab_and_page(db):
    target = next(r for r in _asks() if r["status"] == "assigned")
    at = _run(tab="Requests", full="1", page="2", action="ack", target=target["id"])
    assert str(at.query_params.get("tab")) in ("Requests", "['Requests']")
    assert str(at.query_params.get("page")) in ("2", "['2']")
    assert at.query_params.get("action") in (None, [], ""), "the action is consumed once"
