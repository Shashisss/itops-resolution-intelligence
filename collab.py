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
                "ALTER TABLE delegations ADD COLUMN changed_at TEXT",
                # v110: the delivery stamp and the bundle that travels with the ask. sent_at NULL is
                # the visible NOT SENT state — an ask recorded but never handed to anyone.
                "ALTER TABLE delegations ADD COLUMN sent_at TEXT",
                "ALTER TABLE delegations ADD COLUMN travels TEXT"):
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
                   actor=None, travels=None, delivered=True):
    """Record an ask. ``delivered=False`` creates it in the NOT SENT state (sent_at NULL).

    Every other caller keeps the old meaning: the request was handed over when it was recorded, so
    it carries a sent_at equal to its own timestamp."""
    now = _now()
    who = actor or frm
    con = _connect()
    cur = con.execute(
        "INSERT INTO delegations(ref_id,frm,to_,action,status,ts,channel,stage,actor,changed_at,"
        "sent_at,travels) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (ref_id, frm, to, action, status, now, channel, stage, who, now, now if delivered else None,
         travels))
    _record_event(con, cur.lastrowid, status, who, now)
    con.commit()
    con.close()
    return cur.lastrowid


def retarget_delegations(ref_id, target, actor):
    """Point every open request at a new owner, keeping its deadline and its clock.

    A handover does not finish anybody's work: the asks still need doing, they just have a new
    owner. So only the recipient changes — ts (and therefore the age, the deadline and the overdue
    state) stays exactly as it was, and each row's history records the move."""
    actor = str(actor or "").strip()
    if not actor:
        raise ValueError("a handover requires an actor")
    target = str(target or "").strip()
    if not target:
        raise ValueError("no one to take over")
    now = _now()
    con = _connect()
    rows = [dict(r) for r in con.execute(
        "SELECT id, to_ FROM delegations WHERE ref_id=? AND status!='done'", (ref_id,))]
    for r in rows:
        con.execute("UPDATE delegations SET to_=?, actor=?, changed_at=? WHERE id=?",
                    (target, actor, now, r["id"]))
        _record_event(con, r["id"], "assigned", actor, now)
    con.commit()
    con.close()
    return len(rows)


def send_delegation(did, actor):
    """NOT SENT → SENT: hand a recorded ask over, stamping who sent it and when.

    Returns the HH:MM the send was stamped with (the caller shows it). Sending twice is refused
    rather than silently rewriting the first send time."""
    actor = str(actor or "").strip()
    if not actor:
        raise ValueError("send_delegation requires an actor")
    now = _now()
    con = _connect()
    row = con.execute("SELECT * FROM delegations WHERE id=?", (did,)).fetchone()
    if row is None:
        con.close()
        raise ValueError("no such request")
    if row["sent_at"]:
        con.close()
        raise ValueError("this request was already sent")
    con.execute("UPDATE delegations SET status='assigned', sent_at=?, actor=?, changed_at=? WHERE id=?",
                (now, actor, now, did))
    _record_event(con, did, "assigned", actor, now)
    con.commit()
    con.close()
    return now[11:16]


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
    return now[11:16]


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
