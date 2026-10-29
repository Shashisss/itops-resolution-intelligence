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
def test_freshness_is_one_number_across_the_page(db):
    """The panel, the thread edge and the handoff prose must not print 60m beside 61m.

    They are one measure — now − dop_freshness.last_updated — so one clock per render, one number."""
    import re
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = "INC-8841"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    seen = set(re.findall(r"freshness (\d+)m", md))
    seen |= set(re.findall(r"(\d+)m stale", md))
    seen |= set(re.findall(r"data_age (\d+)", md))
    assert seen, "the page must state the freshness somewhere"
    assert len(seen) == 1, f"freshness printed as several numbers: {sorted(seen)}"


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
    waits = re.findall(r"Waiting \d+m · Data Platform", md)
    slas = re.findall(r"\d+h \d+m left", md)
    assert len(waits) == 1, f"the wait appears {len(waits)} times: {waits}"
    assert len(slas) == 1, f"the SLA clock appears {len(slas)} times: {slas}"
    assert ">Owner<" not in md and ">SLA<" not in md, \
        "the duplicate Owner/SLA fact-card row under the stepper is gone"


def test_hero_strip_on_screen_matches_the_module(db, monkeypatch):
    """The rendered page prints the same three claims story.hero() computes — no second definition.

    Minute figures are compared with the digits normalised: the app aligns its own session copy of
    the database to the wall clock, so a run that crosses a minute boundary may print 53m where the
    fixture computes 54m. The claim (who, what, how many) must be identical."""
    import re
    inc = _inc(db)
    expected = [f["value"] for f in story.hero(inc)["facts"]]
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = "INC-8841"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = "\n".join(m.value for m in at.markdown)
    start = md.index('<div class="ri-hero3">')
    hero = md[start:md.index("</div></div></div>", start)]
    shown = re.findall(r'<div class="v"[^>]*>(.*?)</div>', hero)
    assert len(shown) == 3, shown
    norm = lambda t: re.sub(r"\d+", "#", t)
    for got, want in zip(shown, expected):
        assert norm(got) == norm(want), f"hero shows {got!r}, module computes {want!r}"


def test_hero_is_honest_when_nothing_is_open(db):
    """A closed incident says so instead of inventing a holder or a running clock."""
    inc = _inc(db, "INC-8802")
    h = story.hero(inc)
    assert h["waiting"]["empty"] and h["waiting"]["text"] == "No open request"
    assert h["sla"]["text"] == "closed"


# ------------------------------------------------------------------ the handoff chain
def test_chain_marks_the_current_holder_and_times_each_hop(db):
    inc = _inc(db)
    nodes = story.chain(inc)
    assert [n["holder"] for n in nodes].count(True) == 1
    holder = next(n for n in nodes if n["holder"])
    assert holder["label"] == "Data Platform"
    assert holder["clock"] == "current holder", "the wait is the hero's fact; the hop only says who holds it"
    assert nodes[0]["clock"].endswith("before handoff")
    assert nodes[-1]["label"] == "DOP-1001", "the upstream incident is the last hop"


def test_a_closed_incident_clock_stops_at_closure(db):
    """Six days after closure the chain must still read 'held 40m', not 'held 6d'."""
    inc = _inc(db, "INC-8802")
    nodes = story.chain(inc)
    assert all((n["elapsed_min"] or 0) < 120 for n in nodes), nodes
    assert nodes[0]["clock"] == "held 40m"


# ------------------------------------------------------------------ request cards
def test_request_card_state_follows_the_recorded_transition(db):
    inc = _inc(db)
    card = story.requests(inc["id"])[0]
    assert card["state"] == "overdue", "the seeded request is past its 30m deadline"
    assert card["over_by"] == card["age_min"] - card["deadline_min"]
    assert card["delivered"] is False, "no connector exists — a card may never claim delivery"

    collab.set_delegation_status(card["id"], "accepted", actor=card["owner"])
    assert story.requests(inc["id"])[0]["state"] in ("acknowledged", "overdue")

    collab.set_delegation_status(card["id"], "done", actor=card["owner"])
    assert story.requests(inc["id"])[0]["state"] == "answered"


def test_request_card_states_are_designed():
    """Every state the record can produce has a label and a tone — none falls back to raw status."""
    for status, label in story.STATE_LABEL.items():
        assert label in story.STATE_TONE, f"{status} → {label} has no designed colour"
    assert set(story.STATE_LABEL) == {"assigned", "accepted", "done", "reopened"}


# ------------------------------------------------------------------ acceleration
def test_acceleration_values_come_from_timestamps(db):
    inc = _inc(db)
    a = story.acceleration(inc)
    con = sqlite3.connect(db)
    first_action = con.execute("SELECT MIN(ts) FROM delegations WHERE ref_id=?", (inc["id"],)).fetchone()[0]
    con.close()
    assert a["time_to_next_action_min"] == story.minutes_between(inc["created_at"], first_action)
    assert a["time_to_next_action_what"] == "handed to Data Platform"
    assert a["unblocked_by_evidence_min"] == 18
    assert "JIRA-5521" in a["unblocked_by_evidence_what"]


def test_acceleration_is_an_em_dash_when_the_record_cannot_support_it(db):
    """INC-8850 has no request and no recorded action — the screen shows '—', never a saving."""
    inc = _inc(db, "INC-8850")
    a = story.acceleration(inc)
    assert a["time_to_next_action_min"] is None
    assert a["unblocked_by_evidence_min"] is None
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = "INC-8850"
    at.run()
    md = "\n".join(m.value for m in at.markdown)
    accel = md[md.index('<div class="ri-accel-inline">'):md.index('<div class="ri-accel-inline">') + 600]
    assert accel.count("—") >= 2
    assert "no action recorded yet" in accel


# ------------------------------------------------------------------ learn: inheritance
def test_inheritance_names_the_cause_and_the_runbook():
    recs = learn.records()
    assert recs, "the demo ships learn records — the inheritance block needs one"
    inh = story.inheritance(recs[0])
    assert inh["root_cause"] and inh["root_cause"] != "—"
    assert inh["runbook"], "a runbook the next incident can start with"
    assert inh["ref"]


# ------------------------------------------------------------------ craft: no placeholder copy
def test_incident_page_has_no_placeholder_copy():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = "INC-8841"
    at.run()
    text = "\n".join(
        [m.value for m in at.markdown] + [c.value for c in at.caption]
        + [w.value for w in at.warning] + [e.value for e in at.error]
    )
    for bad in ("TODO", "lorem", "Lorem", "XXX", "coming soon", "placeholder", "TBD"):
        assert bad not in text, f"placeholder copy on the incident page: {bad!r}"
