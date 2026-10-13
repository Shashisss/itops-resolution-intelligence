#!/usr/bin/env python3
"""Collaboration + delegation — shared comment threads and assignment tracking."""
import sqlite3
import datetime as dt

DB = "data/ops.db"


def _now():
    return dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def comments(ref_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM comments WHERE ref_id=? ORDER BY id", (ref_id,))]
    con.close()
    return rows


def add_comment(ref_id, author, role, text):
    if not text.strip():
        return
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO comments(ref_id,author,role,text,ts) VALUES(?,?,?,?,?)",
                (ref_id, author, role, text.strip(), _now()))
    con.commit()
    con.close()


def delegations(ref_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM delegations WHERE ref_id=? ORDER BY id DESC", (ref_id,))]
    con.close()
    return rows


def add_delegation(ref_id, frm, to, action, status="assigned"):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO delegations(ref_id,frm,to_,action,status,ts) VALUES(?,?,?,?,?,?)",
                (ref_id, frm, to, action, status, _now()))
    con.commit()
    con.close()


def set_delegation_status(did, status):
    con = sqlite3.connect(DB)
    con.execute("UPDATE delegations SET status=? WHERE id=?", (status, did))
    con.commit()
    con.close()


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
