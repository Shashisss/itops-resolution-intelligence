#!/usr/bin/env python3
"""Demo clock — keeps the sample data looking live.

The dataset is seeded once and then never changes, so every relative time (SLA remaining, freshness
lag, "asked 4 min ago") drifts as the wall clock moves: a demo opened a day later shows "1h 0m left"
on an incident that should read "3h 12m left", and freshness breaches grow without bound.

`align()` slides every stored timestamp forward so the newest event sits a couple of minutes behind
now. It is a no-op when the data is already fresh, and never changes relative distances — the
scenario keeps its shape while its clock stays plausible.

It runs in two places, because the demo database exists twice: once per process against the seeded
base (data/ops.db), and once per browser session against that session's copy. Aligning only the
process is not enough — a page opened six hours after the process started clones a base aligned six
hours ago, so every incident reads "12h waiting · BREACHED". store.db() re-aligns each copy as it is
made (`align(path=…)`), which is the only place that knows a new session has begun. Passing a path
bypasses the once-per-process memo.
"""
import datetime as dt
import os
import sqlite3

DB = "data/ops.db"

# (table, timestamp column) — every timestamp the UI turns into a relative time.
COLS = [
    ("incidents", "created_at"),
    ("changes", "deployed_at"),
    ("metrics", "ts"),
    ("tickets", "created_at"),
    ("dop_runs", "started_at"),
    ("dop_freshness", "last_updated"),
    ("dop_incidents", "created_at"),
    ("timeline", "ts"),
    ("thread_edges", "ts"),
    ("live_events", "ts"),
    ("comments", "ts"),
    ("delegations", "ts"),
    # v114: the row prints who moved it and when, so those stamps must slide with the rest or the
    # card says "CIO 09:32" on a request the pane reports as 80 minutes old.
    ("delegations", "changed_at"),
    ("delegations", "done_at"),
    ("delegations", "sent_at"),
    ("notifications", "ts"),
    ("resolution_state", "closed_at"),
    ("resolution_state", "updated_at"),
]

_aligned = set()


def _parse(v):
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", ""))
    except Exception:
        return None


ANCHOR = [("incidents", "created_at"), ("dop_incidents", "created_at")]


def align(max_age_min=45, tolerance_min=5, path=None, force=False):
    """Shift all timestamps so the newest one is ~`max_age_min` minutes old.

    Called with no arguments it aligns the seeded base once per process. Called with `path` it
    aligns that database every time (a fresh session copy is a new file, and its whole point is to
    carry a fresh clock). `force` re-aligns even a path already handled in this process.
    """
    target = path or DB
    key = os.path.abspath(target)
    if not os.path.exists(target):
        _aligned.add(key)
        return
    if (key in _aligned) and not force:
        return
    _aligned.add(key)
    try:
        con = sqlite3.connect(target)
    except Exception:
        return
    newest = None
    present = []
    for table, col in ANCHOR:
        try:
            v = con.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
        except Exception:
            continue
        ts = _parse(v)
        if ts and (newest is None or ts > newest):
            newest = ts
    for table, col in COLS:
        try:
            v = con.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
        except Exception:
            continue
        present.append((table, col))
    if newest is None:
        con.close()
        return
    delta = (dt.datetime.now() - dt.timedelta(minutes=max_age_min)) - newest
    if abs(delta.total_seconds()) < tolerance_min * 60:
        con.close()
        return
    for table, col in present:
        try:
            rows = con.execute(f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL").fetchall()
            updates = []
            for rid, val in rows:
                ts = _parse(val)
                if not ts:
                    continue
                moved = (ts + delta).replace(microsecond=0).isoformat(timespec="seconds")
                updates.append((moved, rid))
            if updates:
                con.executemany(f"UPDATE {table} SET {col}=? WHERE rowid=?", updates)
        except Exception:
            continue
    con.commit()
    con.close()
