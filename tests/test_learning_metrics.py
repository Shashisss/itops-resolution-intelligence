"""Learning metrics — accuracy, reuse and the MTTR split, each with its n.

The rule under test: a figure with no sample is a dash, never zero; and a learn record saved after an
incident was raised is not counted as knowledge the responder had.
"""
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

import analytics  # noqa: E402
import journey  # noqa: E402
import learn  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (analytics, journey, learn):
        monkeypatch.setattr(mod, "DB", str(dst))
    monkeypatch.setattr(learn, "PATH", str(tmp_path / "learn.json"))
    return dst


def test_accuracy_counts_decisions_and_reports_its_n(db):
    lg = analytics.learning()
    assert lg["n_records"] >= 4
    assert lg["n_decided"] == lg["counts"]["confirmed"] + lg["counts"]["overridden"]
    assert lg["accuracy"] == round(lg["counts"]["confirmed"] / lg["n_decided"], 3)
    assert lg["counts"]["overridden"] >= 1
    assert lg["n_reused"] >= 1 and lg["reuse_rate"] == round(lg["n_reused"] / lg["n_records"], 3)


def test_empty_sample_is_none_never_zero(db, tmp_path, monkeypatch):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps([]))
    monkeypatch.setattr(learn, "PATH", str(empty))
    lg = analytics.learning()
    assert lg["n_records"] == 0 and lg["n_decided"] == 0
    assert lg["accuracy"] is None, "an empty sample must render as a dash, not 0%"
    assert lg["reuse_rate"] is None
    m = analytics.mttr_by_learn()
    # No record anywhere means no closure had prior knowledge — the "with" group is empty.
    assert m["with"]["median_min"] is None and m["with"]["n"] == 0
    assert m["without"]["n"] == 3 and m["without"]["median_min"] is not None


def test_mttr_split_uses_only_records_saved_before_the_incident(db):
    m = analytics.mttr_by_learn()
    by_ref = {r["ref"]: r for r in m["rows"]}
    # INC-8802 and INC-8711 had a prior record with their own signature; INC-8655 did not.
    assert by_ref["INC-8802"]["matched"] is True
    assert by_ref["INC-8711"]["matched"] is True
    assert by_ref["INC-8655"]["matched"] is False
    assert m["with"]["n"] == 2 and m["without"]["n"] == 1
    assert m["with"]["median_min"] is not None and m["without"]["median_min"] is not None


def test_a_record_saved_after_the_incident_does_not_count_as_prior(db, tmp_path, monkeypatch):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    inc = dict(con.execute("SELECT * FROM incidents WHERE id='INC-8655'").fetchone())
    con.close()
    # Save a record for the same signature — but "now", which is after the incident was raised.
    learn.save(inc, "IT Ops", {"root_cause": "bad deployment", "summary": "rolled back",
                               "steps": "roll back", "outcome": "confirmed"})
    m = analytics.mttr_by_learn()
    row = next(r for r in m["rows"] if r["ref"] == "INC-8655")
    assert row["matched"] is False, "a record saved after the raise cannot have helped resolve it"
    assert m["with"]["n"] == 2 and m["without"]["n"] == 1
