#!/usr/bin/env python3
"""Collaboration + delegation — shared comment threads and assignment tracking."""
import os
import sqlite3
import datetime as dt

import runclock

DB = os.environ.get("RI_DB", "data/ops.db")


def _now():
    return dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def comments(ref_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM comments WHERE ref_id=? ORDER BY id", (ref_id,))]
    con.close()
    return rows


def add_comment(ref_id, author, role, text, channel="App", stage=None):
    if not text.strip():
        return
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO comments(ref_id,author,role,text,ts,channel,stage) VALUES(?,?,?,?,?,?,?)",
                (ref_id, author, role, text.strip(), _now(), channel, stage))
    con.commit()
    con.close()


_ENSURED = set()


def _ensure_state_columns(con):
    """State-audit columns/table, added lazily so an existing database keeps working.

    done_at (v92) is the completion stamp — never backfilled, because a request completed before
    the column existed has no duration and must not be treated as instant. actor/changed_at (v93)
    record *who* made the last transition and *when*; delegation_events keeps every transition."""
    key = str(DB)
    if key in _ENSURED:
        return
    for ddl in ("ALTER TABLE delegations ADD COLUMN done_at TEXT",
                "ALTER TABLE delegations ADD COLUMN actor TEXT",
                "ALTER TABLE delegations ADD COLUMN changed_at TEXT"):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass  # already there
    con.execute("CREATE TABLE IF NOT EXISTS delegation_events("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, delegation_id INTEGER, status TEXT, "
                "actor TEXT, changed_at TEXT)")
    con.commit()
    _ENSURED.add(key)


def _connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    _ensure_state_columns(con)
    return con


def delegations(ref_id):
    con = _connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM delegations WHERE ref_id=? ORDER BY id DESC", (ref_id,))]
    con.close()
    return rows


def delegation_events(did):
    """Every recorded transition of one request, oldest first."""
    con = _connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM delegation_events WHERE delegation_id=? ORDER BY id", (did,))]
    con.close()
    return rows


def _record_event(con, did, status, actor, when):
    con.execute("INSERT INTO delegation_events(delegation_id,status,actor,changed_at) VALUES(?,?,?,?)",
                (did, status, actor, when))


def add_delegation(ref_id, frm, to, action, status="assigned", channel="Teams", stage=None,
                   actor=None):
    now = _now()
    who = actor or frm
    con = _connect()
    cur = con.execute(
        "INSERT INTO delegations(ref_id,frm,to_,action,status,ts,channel,stage,actor,changed_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (ref_id, frm, to, action, status, now, channel, stage, who, now))
    _record_event(con, cur.lastrowid, status, who, now)
    con.commit()
    con.close()


def set_delegation_status(did, status, actor):
    """Move a request to a new state and record who did it, when.

    ``actor`` is required: an unattributed transition makes the collaboration trail unusable for
    review. ``reopened`` is a distinct state (not silently ``assigned``) and clears done_at, so a
    request that is open again has no completion duration."""
    actor = str(actor or "").strip()
    if not actor:
        raise ValueError("set_delegation_status requires an actor")
    status = str(status).lower()
    now = _now()
    con = _connect()
    if status == "done":
        con.execute("UPDATE delegations SET status=?, done_at=?, actor=?, changed_at=? WHERE id=?",
                    (status, now, actor, now, did))
    elif status == "reopened":
        con.execute("UPDATE delegations SET status=?, done_at=NULL, actor=?, changed_at=? WHERE id=?",
                    (status, actor, now, did))
    else:
        con.execute("UPDATE delegations SET status=?, actor=?, changed_at=? WHERE id=?",
                    (status, actor, now, did))
    _record_event(con, did, status, actor, now)
    con.commit()
    con.close()


def age_minutes(d, now=None):
    """Minutes since the request was raised (not since its last transition)."""
    try:
        raised = dt.datetime.fromisoformat(str(d.get("ts")))
    except Exception:
        return 0
    ref = now or runclock.now()
    return max(0, int((ref - raised).total_seconds() / 60))


def is_overdue(d, limit=30):
    """Open longer than the default response expectation — shown, never hidden."""
    return age_minutes(d) > limit


# map a recommendation's "next actor" to a notifiable role
ACTOR_TO_ROLE = {
    "Data Platform": "Data Engineer", "Platform Engineering": "Platform Engineer",
    "Checkout Team": "Developer", "DBA Team": "DBA Team", "Finance Data": "Data Owner",
    "Analytics Engineering": "Data Owner", "Cloud Platform": "Platform Engineer",
}

MENTIONS = {"@dataengineer": "Data Engineer", "@dataowner": "Data Owner",
            "@platformengineer": "Platform Engineer", "@incidentmanager": "Incident Manager",
            "@l2": "L2 / L3 Engineer", "@developer": "Developer", "@csm": "CSM", "@dba": "DBA Team"}


def parse_mentions(text):
    low = text.lower()
    return sorted({role for token, role in MENTIONS.items() if token in low})


def add_notification(role, ref_id, text):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO notifications(role,ref_id,text,ts,read) VALUES(?,?,?,?,0)",
                (role, ref_id, text, _now()))
    con.commit()
    con.close()


def notifications_for(role, limit=12):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM notifications WHERE role=? ORDER BY id DESC LIMIT ?", (role, limit))]
    con.close()
    return rows


def unread_count(role):
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM notifications WHERE role=? AND read=0", (role,)).fetchone()[0]
    con.close()
    return n


def mark_all_read(role):
    con = sqlite3.connect(DB)
    con.execute("UPDATE notifications SET read=1 WHERE role=?", (role,))
    con.commit()
    con.close()


def collaborators():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT DISTINCT author AS who, role, MAX(ts) AS last_ts FROM comments GROUP BY author ORDER BY last_ts DESC")]
    con.close()
    return rows
