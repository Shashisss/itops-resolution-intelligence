"""The story in numbers — every claim on the incident screen traces to one record.

v100 makes three ideas unmistakable: cross-domain, collaboration, accelerated resolution. A number
that states one of them is only allowed on screen if it is a timestamp difference or a count of
stored rows. These tests hold the hero strip, the handoff chain, the request cards and the
acceleration line to that rule, and check that the rendered page shows the same values the module
computes — so the strip cannot drift from the record it came from.
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

import collab  # noqa: E402
import journey  # noqa: E402
import learn  # noqa: E402
import story  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (story, collab, journey):
        monkeypatch.setattr(mod, "DB", str(dst))
    return dst


def _inc(db, ref="INC-8841"):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    row = con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone()
    con.close()
    return dict(row)


# ------------------------------------------------------------------ the hero strip
def test_hero_waiting_is_the_oldest_open_request(db):
    """'Waiting 53m · Data Platform' must be that request's own age and its own recipient."""
    inc = _inc(db)
    asks = [d for d in collab.delegations(inc["id"]) if d["status"] != "done"]
    oldest = min(asks, key=lambda d: d["ts"] or "")
    w = story.waiting(inc)
    assert w["who"] == oldest["to_"]
    assert abs(w["minutes"] - collab.age_minutes(oldest)) <= 1
    assert w["text"] == f'Waiting {story.fmt_minutes(w["minutes"])} · {oldest["to_"]}'


def test_hero_sla_matches_the_priority_clock(db):
    inc = _inc(db)
    s = story.sla(inc)
    target = story.SLA_HOURS[inc["priority"]]
    assert s["target_hours"] == target
    rem_h = target - s["elapsed_hours"]
    assert abs(s["remaining_min"] / 60 - rem_h) < 0.01
    if not s["breached"]:
        assert s["text"] == f'{int(rem_h)}h {int((rem_h % 1) * 60)}m left'


def test_hero_cross_domain_counts_match_the_record(db):
    """3 domains · 2 handoffs: domains are distinct chain domains, handoffs are stored requests."""
    inc = _inc(db)
    c = story.cross(inc)
    assert c["domains"] == len({n["domain"] for n in story.chain(inc)})
    assert c["handoffs"] == len(collab.delegations(inc["id"]))
    assert c["text"] == f'{c["domains"]} domains · {c["handoffs"]} handoffs'
    assert c["domains"] >= 2, "INC-8841 is the cross-domain story — it must show more than one"
def test_wait_sla_and_owner_are_stated_once(db):
    """v103: owner, wait and SLA remaining live in the hero strip and nowhere else on the scroll.

    The old second block under the phase stepper repeated Owner and SLA in large type; the handoff
    prose and the pinned bar repeated the clock again. One instance each, and no card row at all."""
    import re
    inc = _inc(db)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = "INC-8841"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    waits = re.findall(r"<div class=\"v\">Data Platform</div>", md)
    slas = re.findall(r"\d+h \d+m left", md)
    assert len(waits) == 1, f"the holder and wait appear {len(waits)} times: {waits}"
    assert len(slas) == 1, f"the SLA clock appears {len(slas)} times: {slas}"
    assert ">Owner<" not in md and ">SLA<" not in md, \
        "the duplicate Owner/SLA fact-card row under the stepper is gone"


def _tiles(at):
    import re
    md = "\n".join(m.value for m in at.markdown)
    return {k: (v, q) for k, v, q in re.findall(
        r'<div class="k">([^<]+)</div><div class="v">([^<]+)</div><div class="q">([^<]+)</div>', md)}


def _html(ref="INC-8841"):
    import sqlite3
    import incident_html
    con = sqlite3.connect(ROOT / "data" / "ops.db")
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    inc = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return incident_html.build(inc, "DataOps" if ref.startswith("DOP") else "IT Ops",
                               queue="3 of 7", initial_tab="Timeline")


def test_the_tiles_print_what_story_computes(db):
    """The rendered tiles are story's own values — no second definition."""
    import re
    inc = _inc(db)
    h = _html()
    tiles = dict(re.findall(r'<div class="k">([^<]+)</div><div class="v">([^<]+)</div>', h))
    w = story.waiting(inc)
    assert tiles["Waiting on"] == w["who"]
    assert story.sla(inc)["text"] in h, "the single clock, in the header"


def test_wait_sla_and_owner_are_stated_once(db):
    """v109: the holder, the wait and the clock appear once each in the document."""
    import re
    inc = _inc(db)
    h = _html()
    clock = re.findall(r"\d+h \d+m left", h)
    assert len(clock) == 1, f"the clock appears {len(clock)} times: {clock}"
    holder = h.count(f'<div class="v">{story.waiting(inc)["who"]}</div>')
    assert holder == 1, f"the holder appears {holder} times"
    assert "now · held here" in h, "the graph marks the holder without repeating the wait"


def test_freshness_is_one_number_in_the_document(db):
    import re
    h = _html()
    tiles = dict(re.findall(r'<div class="k">([^<]+)</div><div class="v">([^<]+)</div>', h))
    lag = tiles["Data freshness"].rstrip("m")
    assert lag.isdigit(), tiles
    others = set(re.findall(r"STALE (\d+)m", h)) | set(re.findall(r"data_age (\d+)", h))
    assert not others or others == {lag}, f"freshness printed as several numbers: {sorted(others)}"


def test_acceleration_is_an_em_dash_when_the_record_cannot_support_it(db):
    """INC-8850 has no recorded action; nothing on its screen invents a saving."""
    h = _html("INC-8850")
    assert "Time to next action" not in h, "no invented acceleration figure"
