"""Learn — the record that must outlive the session.

A closed incident's learning is the one artefact that cannot live in the per-session demo database:
a page reload replaces that copy. These tests pin the contract — saving writes a durable record,
reading it back returns the same content, and similarity matches on the failure signature.
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

import journey  # noqa: E402
import learn  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    monkeypatch.setattr(journey, "DB", str(dst))
    monkeypatch.setattr(learn, "DB", str(dst))
    monkeypatch.setattr(learn, "PATH", str(tmp_path / "learn.json"))
    return dst


def _row(db, ref):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM incidents WHERE id=?", (ref,)).fetchone()
    con.close()
    return dict(r)


def test_saving_writes_a_durable_record(db, tmp_path):
    inc = _row(db, "INC-8841")
    rec = learn.save(inc, "IT Ops",
                     {"root_cause": "core_ledger schema drift", "summary": "contract v4 replayed",
                      "steps": "reconcile contract v4\nreplay payments_bronze_ingest\nrefresh payments_gold",
                      "outcome": "confirmed", "outcome_by": "Priya (Data Engineer)"},
                     actor="Amit (Incident Manager)")

    assert rec["ref"] == "INC-8841" and rec["signature"] == "it|its_payment_api|unclassified"
    assert rec["steps"] == ["reconcile contract v4", "replay payments_bronze_ingest",
                            "refresh payments_gold"]
    assert rec["outcome"] == "confirmed" and rec["saved_by"] == "Amit (Incident Manager)"

    # Durable: the document is on disk and a fresh read returns the same content.
    on_disk = json.loads((tmp_path / "learn.json").read_text())
    assert "INC-8841" in [r["ref"] for r in on_disk], "the record is on disk, not only in memory"
    assert learn.get("INC-8841")["root_cause"] == "core_ledger schema drift"

    # Editing replaces the record rather than duplicating it.
    learn.save(inc, "IT Ops", {"root_cause": "core_ledger schema drift", "summary": "edited",
                               "steps": "reconcile\nreplay", "outcome": "overridden",
                               "outcome_by": "Amit"})
    recs = [r for r in learn.records() if r["ref"] == "INC-8841"]
    assert len(recs) == 1 and recs[0]["summary"] == "edited" and recs[0]["outcome"] == "overridden"


def test_record_is_retrievable_from_the_incident_and_the_list(db):
    inc = _row(db, "INC-8841")
    assert learn.get("INC-8841") is None
    learn.save(inc, "IT Ops", {"root_cause": "stale upstream", "summary": "replayed",
                               "steps": "replay", "outcome": "confirmed"})
    assert learn.get("INC-8841") is not None                     # from the incident
    assert "INC-8841" in [r["ref"] for r in learn.records()]      # from the Learn list


def test_similarity_matches_the_signature_not_the_service_alone(db):
    # A confirmed upstream cause gives INC-8841 the same signature as the archived INC-8462 record.
    con = sqlite3.connect(db)
    con.execute("UPDATE incidents SET confirmed_cause='UPSTREAM:ds_pay_gd' WHERE id='INC-8841'")
    con.commit()
    con.close()
    inc = _row(db, "INC-8841")
    assert learn.signature(inc, "IT Ops") == "it|its_payment_api|UPSTREAM"
    hits = learn.similar(learn.signature(inc, "IT Ops"), exclude_ref="INC-8841")
    assert [h["ref"] for h in hits] == ["INC-8462"]
    assert hits[0]["steps"], "a similar record must say what fixed it"


def test_signature_separates_components_and_cause_classes(db):
    assert learn.signature({"service_id": "db_payments", "confirmed_cause": "METRIC:M3"}, "IT Ops") \
        == "it|db_payments|METRIC"
    assert learn.signature({"dataset_id": "ds_pay_bz", "confirmed_cause": "RUN:R-9001"}, "DataOps") \
        == "dop|ds_pay_bz|RUN"
    assert learn.signature({"service_id": "its_orders_api", "confirmed_cause": ""}, "IT Ops") \
        == "it|its_orders_api|unclassified"


def test_seeded_records_exist_for_a_fresh_install(db):
    recs = learn.records()
    assert len(recs) >= 4
    assert {"INC-8802", "INC-8711", "INC-8462", "INC-8588"} <= {r["ref"] for r in recs}
    assert any(r["outcome"] == "overridden" for r in recs), "accuracy needs a non-confirmed decision"
    assert any(r.get("reused_from") for r in recs), "reuse needs a record that applied a prior one"
