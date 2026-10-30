"""The incident screen's tabs (v109) — one HTML document, tabs switch client-side.

The screen is no longer built from Streamlit containers, so these assertions live against the
generated document: exactly one pane visible, the tab headers carrying state in words, and the
requested tab opened on load (the server passes ?tab= into the component).
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


def html_for(ref="INC-8841", tab="Timeline"):
    con = sqlite3.connect(ROOT / "data" / "ops.db")
    con.row_factory = sqlite3.Row
    table = "dop_incidents" if ref.startswith("DOP") else "incidents"
    inc = dict(con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone())
    con.close()
    return incident_html.build(inc, "DataOps" if ref.startswith("DOP") else "IT Ops",
                               queue="3 of 7", initial_tab=tab)


def test_incident_opens_on_one_tab_only():
    h = html_for()
    assert h.count('class="pane on"') == 1, "one pane is visible on load"
    assert h.count('class="tab on"') == 1
    assert 'class="pane on" id="p0"' in h, "Timeline is the default"
    assert h.count('class="pane"') == 5, "the other five are rendered but hidden"


def test_each_tab_can_be_selected_on_load():
    for i, name in enumerate(incident_html.TAB_NAMES):
        h = html_for(tab=name)
        assert f'class="pane on" id="p{i}"' in h, name
        assert f'class="tab on" data-t="{i}"' in h, name


def test_tab_headers_carry_counts_and_critical_state():
    h = html_for()
    assert "OVERDUE" in h, "the Requests tab states the overdue ask"
    assert "BLOCKED" in h or "ready" in h, "Act & verify states the gate"
    assert re.search(r'Learn<b>(draft|saved)</b>', h), "Learn states whether the record exists"
    assert re.search(r"Timeline<b>\d+ events</b>", h)


def test_the_panes_do_not_scroll_and_have_no_absolute_positioning():
    h = html_for()
    css = h[h.index("<style>"):h.index("</style>")]
    pane_rule = re.search(r"\.panes\{([^}]*)\}", css).group(1)
    assert "overflow:hidden" in pane_rule, "the pane band clips instead of scrolling"
    assert "position:absolute" not in css, "only the graph SVG may position absolutely"
    assert "height:164px" in pane_rule, "the band is a fixed slice, so the page height is stable"


def test_full_view_is_client_side():
    h = html_for()
    assert 'id="ov"' in h and "ovclose" in h, "the overlay lives inside the same document"
    assert "showall_" not in h, "no Streamlit keys inside the incident screen"
