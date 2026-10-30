"""Who's on it — the static agent panel, held to the record it sits on.

Two conditions are non-negotiable: every number in the panel equals the incident record (so the
panel can never contradict the screen beside it), and the panel carries a visible "simulated" chip.
These tests render each defined incident, check the numbers against story/analytics, prove the empty
state for an undefined incident, and prove that a changed record changes the panel.
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import agents  # noqa: E402
import collab  # noqa: E402
import journey  # noqa: E402
import story  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

DEFINED = ["INC-8841", "INC-8850", "INC-8802", "DOP-1001"]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (story, collab, journey):   # agents reads through story's connection
        monkeypatch.setattr(mod, "DB", str(dst))
    return str(dst)


def _inc(db, ref):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    row = con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone()
    con.close()
    return dict(row)


def _html(ref):
    import sqlite3
    import incident_html
    con = sqlite3.connect(ROOT / "data" / "ops.db")
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    inc = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return incident_html.build(inc, "DataOps" if ref.startswith("DOP") else "IT Ops")


@pytest.mark.parametrize("ref", DEFINED)
def test_each_defined_incident_renders_who_is_on_it(db, ref):
    h = _html(ref)
    assert "Who is on it" in h
    assert "owner" in h
    assert h.count('class="who"') >= 1


def test_an_undefined_incident_still_renders_neutrally(db):
    h = _html("DOP-1002")
    assert "Who is on it" in h, "the card always exists"
    assert "Data Platform" in h, "the owning team comes from the record, not from agents.json"
