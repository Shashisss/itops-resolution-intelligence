#!/usr/bin/env python3
"""Per-session database — makes the demo repeatable.

Every browser session gets its own copy of the seeded database, so executing actions, verifying and
closing an incident never touch the pristine data. Refresh the page and you are back to the original
state; run the same script in front of the next audience without a reset step.

Set RI_DEMO_MODE=0 to work directly on data/ops.db (persistent mode, used by tests and by anyone who
wants the changes to survive).
"""
import glob
import os
import shutil
import time
import uuid

BASE = os.environ.get("RI_BASE_DB", "data/ops.db")
DEMO_OFF = os.environ.get("RI_DEMO_MODE", "1") == "0"
MAX_AGE_MIN = 120
MAX_FILES = 25


def _janitor():
    """Remove session databases left behind by closed tabs — by age, then by count."""
    cutoff = time.time() - MAX_AGE_MIN * 60
    files = sorted(glob.glob("data/session_*.db"), key=os.path.getmtime)
    for path in files:
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass
    files = sorted(glob.glob("data/session_*.db"), key=os.path.getmtime)
    for path in files[:-MAX_FILES]:
        try:
            os.remove(path)
        except OSError:
            pass


def _base_ready():
    """True only when the seeded database exists and is complete (a half-built file is not)."""
    if not os.path.exists(BASE):
        return False
    import sqlite3
    try:
        con = sqlite3.connect(BASE)
        ok = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='delegations'").fetchone()
        con.close()
        return bool(ok)
    except Exception:
        return False


def db():
    """The database this session should use."""
    override = os.environ.get("RI_DB")
    if override:
        return override
    if DEMO_OFF or not _base_ready():
        return BASE
    try:
        import streamlit as st
        path = st.session_state.get("_db_path")
        if path and os.path.exists(path):
            return path
        path = f"data/session_{uuid.uuid4().hex[:8]}.db"
        shutil.copyfile(BASE, path)
        st.session_state["_db_path"] = path
        _janitor()
        return path
    except Exception:
        return BASE


def is_demo():
    """True when this session is disposable (refresh resets it)."""
    return db() != BASE
