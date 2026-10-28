"""One lifecycle, one vocabulary.

The stepper, the audit records and the Analytics funnel must name the same eight stages. A second
list anywhere is a defect: the demo has been burned before by a stage name that only one view knew.
"""
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
import command_center  # noqa: E402
import engine as E  # noqa: E402
import journey  # noqa: E402
import viz  # noqa: E402

EXPECTED = ["Detect", "Triage", "Investigate", "Correlate", "Act", "Verify", "Close", "Learn"]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    src = ROOT / "data" / "ops.db"
    if not src.exists():
        import seed  # noqa: F401
    dst = tmp_path / "ops.db"
    shutil.copy(src, dst)
    for mod in (analytics, journey, E):
        monkeypatch.setattr(mod, "DB", str(dst))
    return dst


def test_the_stage_list_is_defined_once():
    assert journey.LIFECYCLE == EXPECTED
    assert viz.RESOLUTION_FLOW == EXPECTED
    assert analytics.STAGES == EXPECTED


def test_audit_and_funnel_only_name_known_stages():
    assert set(analytics.KIND_STAGE.values()) <= set(EXPECTED)
    assert set(analytics.LEGACY_STAGE.values()) <= set(EXPECTED)
    assert set(analytics.STAGE_OLA_DEFAULT) <= set(EXPECTED)


def test_seeded_ola_targets_are_on_the_stage_list(db):
    con = sqlite3.connect(db)
    stages = {r[0] for r in con.execute("SELECT stage FROM stage_olas")}
    con.close()
    assert stages <= set(EXPECTED)
    assert {"Triage", "Investigate", "Learn"} <= stages, "the new stages need a target too"


def test_thread_spine_uses_the_same_stages(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    inc = dict(con.execute("SELECT * FROM incidents WHERE id='INC-8841'").fetchone())
    con.close()
    items = command_center._thread_spine(inc, deleg=False, confirmed=False, verdict="Investigating")
    assert [i[0] for i in items] == viz.PHASES, "the spine reads as four phases"


def test_every_next_action_names_a_stage_on_the_list(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM incidents")]
    con.close()
    for inc in rows:
        assert journey.next_action(inc)["stage"] in EXPECTED, inc["id"]


def test_four_phases_cover_the_eight_stages_exactly_once():
    """v99: the stepper shows phases; the stages are untouched underneath."""
    assert viz.PHASES == ["Detect", "Resolve", "Act & Verify", "Close & Learn"]
    covered = []
    for phase in viz.PHASES:
        covered += viz.stages_in_phase(phase)
    assert covered == EXPECTED, "every stage belongs to exactly one phase, in order"
    assert journey.phase_of("Detect") == "Detect"
    assert journey.phase_of("Triage") == journey.phase_of("Investigate") == journey.phase_of("Correlate") == "Resolve"
    assert journey.phase_of("Act") == journey.phase_of("Verify") == "Act & Verify"
    assert journey.phase_of("Close") == journey.phase_of("Learn") == "Close & Learn"
    assert journey.PHASES == viz.PHASES
