"""Milestone 2 — analytics computed from real lifecycle timestamps.

The rule under test: every figure is measured from stored timestamps, a missing record is unknown
(never zero), an unfinished handoff has no delay, and a sample smaller than five is flagged rather
than dressed up.
"""
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

import analytics  # noqa: E402
import collab  # noqa: E402
import journey  # noqa: E402

SCRUB = ("resolution_state", "timeline", "comments", "delegations", "notifications",
         "incidents", "dop_incidents")


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """A throwaway copy of the demo database, emptied of every table these panels read."""
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401  (creates it)
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (analytics, journey, collab):
        monkeypatch.setattr(mod, "DB", str(dst))
    journey._ensure_resolution_table()
    con = sqlite3.connect(dst)
    for table in SCRUB:
        con.execute(f"DELETE FROM {table}")
    con.commit()
    con.close()
    return dst


def incident(con, ref, created="2026-01-01T10:00:00", status="open", priority="P2",
             table="incidents"):
    con.execute(
        f"INSERT INTO {table}(id,title,priority,status,created_at,stage,owner_team) "
        "VALUES(?,?,?,?,?,?,?)",
        (ref, f"Test incident {ref}", priority, status, created, "Detected", "Test Team"))


def verified(con, ref, closed, verdict="Verified"):
    con.execute("INSERT OR REPLACE INTO resolution_state(ref_id,verdict,action_id,actor,closed_at,"
                "updated_at,checks) VALUES(?,?,?,?,?,?,?)",
                (ref, verdict, "A1", "Verification service", closed, closed,
                 '[{"check": "error rate", "result": "\\u2705 pass"}]'))


def event(con, ref, ts, kind, detail="test event"):
    con.execute("INSERT INTO timeline(id,ref_id,domain,ts,kind,detail) VALUES(?,?,?,?,?,?)",
                (f"E-{ref}-{kind}-{ts}", ref, "itops", ts, kind, detail))


def test_mttr_of_a_fixed_timestamp_incident(db):
    con = sqlite3.connect(db)
    incident(con, "INC-A", created="2026-01-01T10:00:00")
    verified(con, "INC-A", "2026-01-01T11:00:00")          # exactly 60 minutes
    incident(con, "INC-B", created="2026-01-02T09:00:00")
    verified(con, "INC-B", "2026-01-02T09:30:00")          # exactly 30 minutes
    con.commit()
    con.close()

    m = analytics.mttr()
    assert m["n"] == 2
    assert m["median_min"] == 45.0
    assert m["p90_min"] == 57.0, "p90 must interpolate between 30 and 60"
    assert sorted(m["values"]) == [30.0, 60.0]


def test_stage_median_from_a_synthetic_timeline(db):
    con = sqlite3.connect(db)
    incident(con, "INC-S1", created="2026-01-01T09:55:00")
    event(con, "INC-S1", "2026-01-01T10:00:00", "alert")
    event(con, "INC-S1", "2026-01-01T10:20:00", "ticket")
    event(con, "INC-S1", "2026-01-01T11:00:00", "verify")
    incident(con, "INC-S2", created="2026-01-01T09:55:00")
    event(con, "INC-S2", "2026-01-01T12:00:00", "alert")
    event(con, "INC-S2", "2026-01-01T12:30:00", "ticket")   # Detect 30, Correlate unmeasured
    con.commit()
    con.close()

    rows = {r["stage"]: r for r in analytics.stage_durations()["rows"]}
    # Detect: 20 min and 30 min → median 25
    assert rows["Detect"]["n"] == 2 and rows["Detect"]["median_min"] == 25.0
    # Correlate: only INC-S1 measured (10:20 → 11:00 = 40); INC-S2 has no next stage
    assert rows["Correlate"]["n"] == 1 and rows["Correlate"]["median_min"] == 40.0
    assert rows["Verify"]["median_min"] is None and rows["Verify"]["n"] == 0
    assert rows["Detect"]["indicative"] is True, "two samples are indicative, not significant"


def test_ola_delta_sign_follows_the_measurement(db):
    con = sqlite3.connect(db)
    # Detect: 40 minutes against a 5-minute target → over by 35
    incident(con, "INC-D1", created="2026-01-01T09:00:00")
    event(con, "INC-D1", "2026-01-01T10:00:00", "alert")
    event(con, "INC-D1", "2026-01-01T10:40:00", "ticket")
    # Act: 2 minutes against a 30-minute target → comfortably inside
    incident(con, "INC-D2", created="2026-01-01T12:00:00")
    event(con, "INC-D2", "2026-01-01T12:00:00", "alert")
    event(con, "INC-D2", "2026-01-01T12:01:00", "ticket")
    event(con, "INC-D2", "2026-01-01T12:05:00", "repair")
    event(con, "INC-D2", "2026-01-01T12:07:00", "verify")
    con.commit()
    con.close()

    rows = {r["stage"]: r for r in analytics.ola_vs_actual()["rows"]}
    assert rows["Act"]["actual_min"] == 2.0 and rows["Act"]["target_min"] == 30
    assert rows["Act"]["delta_min"] == -28.0 and rows["Act"]["state"] == "within"
    # Detect across both incidents: 40 and 1 minute → median 20.5, still over the 5-minute target
    assert rows["Detect"]["actual_min"] == 20.5 and rows["Detect"]["target_min"] == 5
    assert rows["Detect"]["delta_min"] == 15.5 and rows["Detect"]["state"] == "over", \
        "a positive delta means the stage ran longer than its OLA"


def test_handoff_delay_and_a_never_completed_request(db):
    con = sqlite3.connect(db)
    incident(con, "INC-H1")
    con.commit()
    con.close()

    collab.add_delegation("INC-H1", "Incident Manager", "Data Platform", "confirm contract")
    collab.add_delegation("INC-H1", "Incident Manager", "DBA Team", "confirm rollback")

    con = sqlite3.connect(db)
    rows = con.execute("SELECT id,action FROM delegations ORDER BY id").fetchall()
    done_id = rows[0][0]
    open_id = rows[1][0]
    ten_ago = (dt.datetime.now() - dt.timedelta(minutes=10)).replace(microsecond=0).isoformat(timespec="seconds")
    forty_ago = (dt.datetime.now() - dt.timedelta(minutes=40)).replace(microsecond=0).isoformat(timespec="seconds")
    con.execute("UPDATE delegations SET ts=? WHERE id=?", (ten_ago, done_id))
    con.execute("UPDATE delegations SET ts=? WHERE id=?", (forty_ago, open_id))
    con.commit()
    con.close()

    collab.set_delegation_status(done_id, "done", actor="DBA Team")   # stamps done_at lazily

    h = analytics.handoff_delay()
    assert h["n_done"] == 1
    assert h["median_min"] == pytest.approx(10, abs=0.2), "delay is done_at − ts"
    assert h["n_open"] == 1, "the never-completed request is not a delay sample"
    assert h["open_over_30"] == 1 and h["open_share_over_30"] == 1.0


def test_an_incident_without_a_resolution_record_is_excluded_not_zero(db):
    con = sqlite3.connect(db)
    incident(con, "INC-N1", created="2026-01-01T10:00:00")
    verified(con, "INC-N1", "2026-01-01T10:20:00")             # 20 minutes
    incident(con, "INC-N2", created="2026-01-01T10:00:00", status="closed")   # closed, no record
    incident(con, "INC-N3", created="2026-01-01T10:00:00")
    verified(con, "INC-N3", "2026-01-01T10:40:00", verdict="Mitigated")       # not a closure
    con.commit()
    con.close()

    m = analytics.mttr()
    assert m["n"] == 1, "only the verified record with a closure time is a sample"
    assert m["values"] == [20.0], "a missing record must not be counted as a zero-minute closure"
    assert m["median_min"] == 20.0
    assert m["excluded_no_record"] == 1              # INC-N2
    assert m["excluded_unverified"] == 1             # INC-N3

    o = analytics.outcomes()
    assert o["n_records"] == 2 and o["n_incidents"] == 3
    assert o["counts"]["Verified"] == 1 and o["counts"]["Mitigated"] == 1
    assert o["verified_rate"] == 0.5
    assert o["no_record"] == 1
