"""Collaboration regression — every transition is attributed, reopened is its own state, and an
overdue request is visible rather than silent."""
import datetime as dt
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


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setattr(collab, "DB", str(dst))
    con = sqlite3.connect(dst)
    con.execute("DELETE FROM delegations")
    con.commit()
    con.close()
    return dst


def test_request_ack_complete_reopen_records_actor_each_time(db):
    collab.add_delegation("INC-8841", "Incident Manager", "Data Platform",
                          "confirm contract v4", channel="Teams")
    d = collab.delegations("INC-8841")[0]
    assert d["status"] == "assigned"
    assert d["actor"] == "Incident Manager", "creation is itself a recorded transition"
    assert d["changed_at"] and d["ts"]

    collab.set_delegation_status(d["id"], "accepted", actor="Data Platform")
    d = collab.delegations("INC-8841")[0]
    assert d["status"] == "accepted" and d["actor"] == "Data Platform"

    collab.set_delegation_status(d["id"], "done", actor="Data Platform")
    d = collab.delegations("INC-8841")[0]
    assert d["status"] == "done" and d["actor"] == "Data Platform"
    assert d["done_at"], "completion must be stamped"
    first_done = d["done_at"]

    collab.set_delegation_status(d["id"], "reopened", actor="Incident Manager")
    d = collab.delegations("INC-8841")[0]
    assert d["status"] == "reopened", "reopened must not silently become assigned"
    assert d["actor"] == "Incident Manager"
    assert d["done_at"] is None, "a reopened request has no completion duration"
    assert d["done_at"] != first_done

    events = collab.delegation_events(d["id"])
    assert [e["status"] for e in events] == ["assigned", "accepted", "done", "reopened"]
    assert [e["actor"] for e in events] == ["Incident Manager", "Data Platform",
                                            "Data Platform", "Incident Manager"]
    assert all(e["changed_at"] for e in events), "every transition carries its own timestamp"


def test_transition_without_an_actor_is_refused(db):
    collab.add_delegation("INC-8841", "Incident Manager", "DBA Team", "check locks")
    did = collab.delegations("INC-8841")[0]["id"]
    with pytest.raises(ValueError):
        collab.set_delegation_status(did, "accepted", actor=" ")


def test_overdue_is_computed_from_the_request_time(db):
    collab.add_delegation("INC-8841", "Incident Manager", "DBA Team", "check locks")
    d = collab.delegations("INC-8841")[0]
    now = dt.datetime.fromisoformat(d["ts"])
    old = dict(d, ts=(now - dt.timedelta(minutes=45)).isoformat(timespec="seconds"))
    fresh = dict(d, ts=(now - dt.timedelta(minutes=5)).isoformat(timespec="seconds"))
    assert collab.age_minutes(old, now=now) == 45
    assert collab.is_overdue(old, 30) is True
    assert collab.is_overdue(fresh, 30) is False
