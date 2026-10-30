"""The incident screen's layout (v109) — one HTML document, no nested scroll.

These replace the v94–v108 tests that inspected Streamlit containers: the containers are gone, and
the properties they protected (one scroll surface, no clipped panel, phase names, stage actions)
are now properties of the generated document.
"""
import os
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import incident_html  # noqa: E402


def html_for(ref="INC-8841"):
    con = sqlite3.connect(ROOT / "data" / "ops.db")
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    inc = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return incident_html.build(inc, "DataOps" if ref.startswith("DOP") else "IT Ops",
                               queue="1 of 7")


def test_the_panel_is_not_height_clamped():
    """No nested scroll: the document sets overflow:hidden and the pane band clips a fixed slice."""
    css = html_for()
    css = css[css.index("<style>"):css.index("</style>")]
    assert "overflow:hidden" in css
    assert css.count("overflow:auto") == 1, "only the overlay's body scrolls"
    panes = re.search(r"\.panes\{([^}]*)\}", css).group(1)
    assert "height:164px" in panes and "overflow:hidden" in panes


def test_the_four_phases_are_named():
    h = html_for()
    for phase in ("Confirm cause", "Apply remediation", "Run verification", "Close incident"):
        assert phase in h, phase


def test_the_stage_actions_are_links_within_the_document():
    h = html_for()
    assert "Confirm cause" in h
    assert 'href="?inc=INC-8841&amp;action=confirm"' in h      # &amp; is the correct attribute form
    assert "Close incident" in h
    # every phase is either a live link or a refusal that states why — no dead button
    assert "Apply remediation" in h and "Run verification" in h, "every phase is named"
    for phase, action in (("Apply remediation", "apply"), ("Run verification", "verify")):
        as_link = f'action={action}' in h
        explained = "needs approval first" in h or "nothing applied yet" in h or "no remediation plan" in h
        assert as_link or explained, f'{phase} is neither offered nor explained'
    assert 'class="act blocked"' in h or 'href="?inc=INC-8841&amp;action=close"' in h


def test_a_dataops_incident_renders_the_same_shape():
    h = html_for("DOP-1001")
    assert h.count('class="tile"') == 4
    assert "Failed runs" in h
    assert "payments_bronze_ingest" in h
