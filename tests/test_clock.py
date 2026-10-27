"""Demo clock — a session copy must not inherit the clock the process started with.

The base database is aligned once per process. A tab opened six hours later used to clone that base
unchanged, so every incident read "12h waiting · BREACHED" on a deploy that had been up since the
morning. store.db() now re-aligns each copy as it is made; these tests pin that down.
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

import clock  # noqa: E402
import store  # noqa: E402


def _stale_db(path, hours_ago=12):
    """A minimal database whose newest timestamp is `hours_ago` behind the wall clock."""
    when = (dt.datetime.now() - dt.timedelta(hours=hours_ago)).replace(microsecond=0)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS incidents (created_at TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS timeline (ts TEXT)")
    con.execute("DELETE FROM incidents")
    con.execute("DELETE FROM timeline")
    con.execute("INSERT INTO incidents VALUES (?)", (when.isoformat(timespec="seconds"),))
    con.execute("INSERT INTO timeline VALUES (?)", ((when + dt.timedelta(minutes=5)).isoformat(timespec="seconds"),))
    con.commit()
    con.close()
    return when


def _newest(path):
    con = sqlite3.connect(path)
    value = con.execute("SELECT MAX(created_at) FROM incidents").fetchone()[0]
    con.close()
    return dt.datetime.fromisoformat(value)


def _age_minutes(path):
    return (dt.datetime.now() - _newest(path)).total_seconds() / 60


def test_align_accepts_an_explicit_path(tmp_path):
    db = tmp_path / "stale.db"
    _stale_db(db)
    assert _age_minutes(db) > 600

    clock.align(path=str(db))

    # newest sits max_age_min (45) behind now, allow for the test's own runtime
    assert 40 <= _age_minutes(db) <= 50, _age_minutes(db)


def test_align_is_memoised_per_path_until_forced(tmp_path):
    db = tmp_path / "again.db"
    _stale_db(db)
    clock.align(path=str(db))

    clock.align(path=str(db))          # same path, already handled: no-op even if the file aged
    _stale_db(db)                      # simulate hours passing on a long-running process
    clock.align(path=str(db))
    assert _age_minutes(db) > 600, "a memoised path is skipped"

    clock.align(path=str(db), force=True)   # an explicit re-align is honoured
    assert 40 <= _age_minutes(db) <= 50


def test_session_copy_is_realigned_while_the_base_is_left_alone(tmp_path):
    base = tmp_path / "ops.db"
    _stale_db(base)
    base_age = _age_minutes(base)

    copy = tmp_path / "session_abc123.db"
    shutil.copyfile(base, copy)
    store._align_copy(str(copy))

    assert 40 <= _age_minutes(copy) <= 50, "the copy a browser session gets must look live"
    assert _age_minutes(base) == pytest.approx(base_age, abs=1), "the base keeps its own clock"


def test_align_ignores_a_missing_file(tmp_path):
    clock.align(path=str(tmp_path / "nope.db"))   # must not raise
    assert not os.path.exists(tmp_path / "nope.db")
