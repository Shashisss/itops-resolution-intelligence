"""Share, comments and bringing someone in (v124).

Same rule as every other pass: the action is driven through the app with a query parameter, then the
record *and* the re-rendered document are read back.
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
import incident_html  # noqa: E402
import journey  # noqa: E402
import learn  # noqa: E402
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
    monkeypatch.setenv("RI_LEARN_PATH", str(tmp_path / "learn.json"))
    for mod in (journey, collab, story):
        monkeypatch.setattr(mod, "DB", str(dst))
    journey._ensure_resolution_table()
    journey._ensure_remediation_table()
    journey._ensure_lead_table()
    return dst


def _inc(ref=REF):
    con = sqlite3.connect(collab.DB)
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    row = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return row


def _html(tab="Timeline", view=None, ref=REF):
    inc = _inc(ref)
    v = {"tab": tab, "base": "https://example.streamlit.app", "you": "CIO",
         "owners": ["Data Platform", "Checkout Team", "Finance Data", "CIO"]}
    v.update(view or {})
    return incident_html.build(inc, "DataOps" if ref.startswith("DOP") else "IT Ops",
                               queue="3 of 7", initial_tab=tab, view=v,
                               owners=v["owners"])


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


# ---------------------------------------------------------------- share
def test_the_share_pane_states_the_summary_and_the_deep_link(db):
    inc = _inc()
    h = _html(view={"share": True})
    text = re.search(r'<pre class="sharetext" id="sharetext">(.*?)</pre>', h, re.S).group(1)
    import html as _h
    body = _h.unescape(text)
    assert inc["id"] in body and inc["title"] in body
    assert journey.lifecycle_stage(inc) in body
    assert inc["owner_team"] in body, "the holder is named"
    assert (inc.get("blocker") or "—") in body, "the blocker is named"
    assert "next " in body, "the next action is named"
    assert f'https://example.streamlit.app/?inc={REF}' in body, "a read-only deep link"
    assert 'data-copy="sharetext"' in h, "a Copy control"
    assert "select the text" in h, "a plain selectable fallback"
    assert 'id="ov"' in h and 'class="ov on"' not in h, "no modal"


def test_share_records_it_in_the_audit_with_actor_and_time(db):
    # opening the share pane is done by the header link, which carries ?action=share
    _run(tab="Timeline", share="1", action="share")
    events = journey.timeline(REF)
    shared = [e for e in events if "Shared by" in (e.get("detail") or "")]
    assert shared, "the share is in the audit trail"
    assert "Shared by" in shared[-1]["detail"] and re.search(r"\d{2}:\d{2}", shared[-1]["detail"])
    said = [c for c in collab.comments(REF) if "portal summary" in (c.get("text") or "")]
    assert said and said[-1]["channel"] == "Portal"


# ---------------------------------------------------------------- comments
def test_a_comment_is_posted_and_rendered_with_author_channel_and_time(db):
    at = _run(tab="Timeline", action="comment", text="SUP-4471 attached the ledger trace.")
    assert "Comment posted" in _flash(at)
    last = collab.comments(REF)[-1]
    assert last["text"] == "SUP-4471 attached the ledger trace."
    assert last["author"] and last["channel"] == "Portal" and last["ts"]
    h = _html(tab="Timeline")
    line = [l for l in h.split("<div class=\"ev cmtline\"") if "SUP-4471" in l][0]
    assert last["author"] in line and "Portal" in line and last["ts"][11:16] in line


def test_an_empty_comment_is_rejected_out_loud(db):
    before = len(collab.comments(REF))
    at = _run(tab="Timeline", action="comment", text="   ")
    assert "needs text" in _flash(at), "a refusal the reader can see"
    assert len(collab.comments(REF)) == before, "nothing was written"


def test_comments_are_newest_last(db):
    _run(tab="Timeline", action="comment", text="first note")
    _run(tab="Timeline", action="comment", text="second note")
    h = _html(tab="Timeline")
    assert h.index("first note") < h.index("second note"), "the thread reads in order"


# ---------------------------------------------------------------- bring someone in
def test_bring_in_lists_the_records_teams_and_posts_the_assign(db):
    h = _html(view={"assign": True})
    rows = re.findall(r'<a class="pk" href="([^"]+)"[^>]*>([^<]+)</a>', h)
    assert rows, "the picker lists people from the record"
    for href, name in rows:
        assert "action=assign" in href and "target=" in href
    assert 'id="ov"' in h and 'class="ov on"' not in h, "no modal"


def test_assigning_changes_owner_keeps_the_old_one_and_restarts_the_clock(db):
    inc0 = _inc()
    old_owner = inc0["owner_team"]
    target = "Checkout Team" if old_owner != "Checkout Team" else "Finance Data"
    at = _run(tab="Timeline", action="assign", target=target)
    assert f"Brought in {target}" in _flash(at)

    inc = _inc()
    assert inc["owner_team"] == target, "the incident is owned by the new team"
    # the previous holder is still on the thread, as a done request
    handovers = [d for d in collab.delegations(REF)
                 if d["status"] == "done" and d["to_"] == old_owner]
    assert handovers, "the previous holder's open ask was closed, not deleted"
    # the new owner holds it now: the ask clock starts at the handover
    w = story.waiting(inc)
    assert w["who"] == target, "the holder is the new owner"
    assert w["minutes"] <= 2, "the ask clock restarted with the handover"
    # and the audit says who did it when
    ev = [e for e in journey.timeline(REF) if "Brought in" in (e.get("detail") or "")]
    assert ev and re.search(r"\d{2}:\d{2}", ev[-1]["detail"])

    h = _html()
    i = h.index("Who is on it")
    who = h[i:i + 700]                              # the who card, bounded by its own rows
    assert target in who, "who-card shows the new owner"
    assert old_owner in who, "the previous holder is on the thread"
    assert "Waiting on" in h


def test_the_waiting_tile_follows_the_new_owner(db):
    target = "Finance Data" if _inc()["owner_team"] != "Finance Data" else "Checkout Team"
    _run(tab="Timeline", action="assign", target=target)
    h = _html()
    tiles = re.findall(r'<div class="k">([^<]+)</div><div class="v">([^<]+)</div>', h)
    waiting = dict(tiles)["Waiting on"]
    assert waiting == target, f"the Waiting on tile reads {waiting!r}"


def test_assigning_the_current_owner_is_refused(db):
    owner = _inc()["owner_team"]
    at = _run(tab="Timeline", action="assign", target=owner)
    assert "already owns" in _flash(at)
    assert _inc()["owner_team"] == owner
