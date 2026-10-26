#!/usr/bin/env python3
"""Demo clock — keeps the sample data looking live.

The dataset is seeded once and then never changes, so every relative time (SLA remaining, freshness
lag, "asked 4 min ago") drifts as the wall clock moves: a demo opened a day later shows "1h 0m left"
on an incident that should read "3h 12m left", and freshness breaches grow without bound.

`align()` slides every stored timestamp forward so the newest event sits a couple of minutes behind
now. It runs once per process, is a no-op when the data is already fresh, and never changes relative
distances — the scenario keeps its shape while its clock stays plausible.
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
    ("notifications", "ts"),
    ("resolution_state", "closed_at"),
    ("resolution_state", "updated_at"),
]

_done = False


def _parse(v):
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", ""))
    except Exception:
        return None


ANCHOR = [("incidents", "created_at"), ("dop_incidents", "created_at")]


def align(max_age_min=45, tolerance_min=5):
    """Shift all timestamps so the newest one is ~`max_age_min` minutes old. Idempotent."""
    global _done
    if _done or not os.path.exists(DB):
        _done = True
        return
    _done = True
    try:
        con = sqlite3.connect(DB)
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
