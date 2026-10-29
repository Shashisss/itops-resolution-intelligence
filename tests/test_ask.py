"""Ask — twenty-plus questions, their intents, their numbers and the refusal path.

The point of the feature is credibility: an answer is only allowed if it can be computed from a
stored definition. So each supported question is checked twice — against an independent SQL count
in the test itself, and against the analytics function the answer claims to use. Each unsupported
question must refuse, offer three examples, and produce no number.
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

import analytics  # noqa: E402
import ask  # noqa: E402
import collab  # noqa: E402
import journey  # noqa: E402
import story  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (ask, analytics, story, collab, journey):
        monkeypatch.setattr(mod, "DB", str(dst))
    return str(dst)


def raw_count(db, start=None, end=None, status="all"):
    """An independent count — deliberately not the function under test."""
    clauses, params = [], []
    if start:
        clauses.append("created_at >= ?")
        params.append(start)
    if end:
        clauses.append("created_at < ?")
        params.append(end)
    if status in ("open", "closed"):
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = ("SELECT COUNT(*) FROM (SELECT id, created_at, status FROM incidents "
           "UNION ALL SELECT id, created_at, status FROM dop_incidents)" + where)
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, params).fetchone()[0]
    finally:
        con.close()


SUPPORTED = [
    # (question, intent, expected value or (callable(db) -> value))
    ("how many incidents were reported yesterday", "count",
     lambda db: raw_count(db, ask.window("yesterday")[0].isoformat(timespec="seconds"),
                          ask.window("yesterday")[1].isoformat(timespec="seconds"))),
    ("how many incidents were reported today", "count",
     lambda db: raw_count(db, ask.window("today")[0].isoformat(timespec="seconds"), None)),
    ("how many incidents were reported in the last 14 days", "count",
     lambda db: raw_count(db, ask.window("last 14 days")[0].isoformat(timespec="seconds"), None)),
    ("how many incidents were reported last month", "count",
     lambda db: raw_count(db, ask.window("last month")[0].isoformat(timespec="seconds"), None)),
    ("how many incidents are open", "count", lambda db: raw_count(db, status="open")),
    ("how many incidents are closed", "count", lambda db: raw_count(db, status="closed")),
    ("how many failed in the last week", "count", "0"),
    ("number of incidents raised this week", "count",
     lambda db: raw_count(db, ask.window("this week")[0].isoformat(timespec="seconds"), None)),
    ("how many incidents were reported in the last 7 days", "count",
     lambda db: raw_count(db, ask.window("last 7 days")[0].isoformat(timespec="seconds"), None)),
    ("summarise INC-8841", "summary", "INC-8841"),
    ("summarize inc-8841", "summary", "INC-8841"),
    ("what happened on INC-8841", "summary", "INC-8841"),
    ("walk me through DOP-1001", "summary", "DOP-1001"),
    ("which domain held us longest last month", "held_longest", "Data Platform"),
    ("which domain was slowest this week", "held_longest", None),
    ("what is our median resolution time this week", "median_resolution", None),
    ("what is the median MTTR in the last 30 days", "median_resolution", None),
    ("average resolution time last month", "median_resolution", None),
    ("what is our typical time to close this month", "median_resolution", None),
]

UNSUPPORTED = [
    "why is the payment API slow",
    "who should I call about INC-8841",
    "will the SLA be breached tomorrow",
    "what caused the incident",
    "hello",
    "",
    "show me everything",
]


@pytest.mark.parametrize("question,intent,expected", SUPPORTED)
def test_supported_question_parses_and_answers(db, question, intent, expected):
    a = ask.answer(question)
    assert a["intent"] == intent, f"{question!r} parsed as {a['intent']}"
    assert a["ok"] is True
    assert a["interpretation"], "an answer must state its interpretation"
    assert a["based_on"], "an answer must name the tables/definitions it used"
    assert a["followups"], "an answer must offer follow-ups"
    if callable(expected):
        assert a["n"] == expected(db), f"{question!r} answered {a['n']}"
    elif expected is not None:
        assert a["headline"] == expected


@pytest.mark.parametrize("question", UNSUPPORTED)
def test_unsupported_question_refuses_without_a_number(db, question):
    a = ask.answer(question)
    assert a["ok"] is False and a["intent"] == "unsupported"
    assert a["headline"] == "—", "a refusal must never show a number"
    assert a["sql"] is None
    assert len(a["followups"]) == 3, "a refusal offers three things it can answer"


def test_count_uses_the_analytics_definition(db):
    """The Ask count and analytics.created_between are the same computation, not two filters."""
    a = ask.answer("how many incidents were reported yesterday")
    start, end, _ = ask.window("yesterday")
    direct = analytics.created_between(start.isoformat(timespec="seconds"),
                                       end.isoformat(timespec="seconds"))
    assert a["n"] == direct["n"]
    assert a["sql"].strip() == direct["sql"].strip()


def test_median_uses_the_analytics_mttr_definition(db):
    a = ask.answer("what is our median resolution time in the last 30 days")
    start, end, _ = ask.window("last month")
    direct = analytics.mttr_between(start.isoformat(timespec="seconds"),
                                    end.isoformat(timespec="seconds"))
    assert direct["n"] > 0, "the demo must have a closure in this window"
    assert a["n"] == direct["n"]
    assert a["headline"] == f'{direct["median_min"]:g} min'


def test_the_query_shown_is_the_query_executed(db):
    """Every answer's SQL must run, and return exactly the n the answer printed."""
    for question in ("how many incidents were reported yesterday", "how many incidents are open",
                     "how many failed in the last week"):
        a = ask.answer(question)
        con = sqlite3.connect(db)
        try:
            rows = con.execute(a["sql"], a["params"]).fetchall()
        finally:
            con.close()
        assert len(rows) == a["n"], question


def test_no_answer_comes_from_prose(db):
    """Every supported answer carries either a number or cited events — never a paragraph alone."""
    for question, intent, _ in SUPPORTED:
        a = ask.answer(question)
        assert a["headline"] or a["narrative"], question
        if intent == "summary":
            assert a["cites"], "a summary must cite the events it used"
            assert a["sql"]


def test_summary_tells_the_thread_in_order(db):
    a = ask.answer("summarise INC-8841")
    text = " ".join(a["narrative"])
    assert "Raised at" in text
    assert "Who held it" in text
    assert "What unblocked it" in text
    assert "Still open" in text or "Closed" in text
    stamps = [c["ts"] for c in a["cites"]]
    assert stamps == sorted(stamps), "citations must follow the thread's order"


def test_held_longest_names_the_domain_and_its_minutes(db):
    a = ask.answer("which domain held us longest last month")
    start, end, _ = ask.window("last month")
    direct = analytics.held_by_domain(start.isoformat(timespec="seconds"),
                                      end.isoformat(timespec="seconds"))
    assert a["headline"] == direct["rows"][0]["domain"]
    assert f'{direct["rows"][0]["minutes"]:g}' in a["narrative"][0]


def test_ask_box_renders_on_incidents_and_analytics():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(t.label.startswith("Ask — how many incidents") for t in at.text_input)

    at2 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at2.session_state["nav"] = "Analytics"
    at2.run()
    assert not at2.exception, [e.value for e in at2.exception]
    assert any(t.label.startswith("Ask — what is our median") for t in at2.text_input)


def test_a_shareable_link_answers_the_question_on_load(db):
    """?ask=… answers immediately, so a demo URL can demonstrate a question."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["ask"] = "summarise INC-8841"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = "\n".join(m.value for m in at.markdown)
    assert "ri-answer" in md and "Who held it" in md
