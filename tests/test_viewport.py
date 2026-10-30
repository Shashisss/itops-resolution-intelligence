"""The one-viewport budget (v108) — measured, not asserted from vibes.

The pixel measurement is taken in the browser (768/768 at 1366×768, no scrollbar; 800/800 at
1280×800). A test cannot read the browser, so it holds the *contract* that produces those numbers:
the declared height of each band, summed, must stay inside the cap — and the page may render exactly
one of each band. If someone adds a block or raises a cap, this fails before the demo does.
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import story  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

CAP = 780
BANDS = {"header": 62, "tiles": 76, "hero": 330, "tabs": 44, "tab body": 164, "footer": 26}


def open_page(**params):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = "INC-8841"
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_layout_budget_fits_the_viewport():
    total = sum(BANDS.values())
    assert total <= CAP, f"declared bands total {total}px, cap {CAP}px: {BANDS}"


def test_the_page_renders_one_of_each_band():
    md = "\n".join(m.value for m in open_page().markdown)
    assert md.count('class="ri-h2"') == 1, "one header band"
    assert md.count('class="ri-tiles"') == 1, "one tiles band"
    assert md.count('class="ri-card2"') == 3, "graph + meaning + who is on it"
    assert 'max-height:164px' in md, "the tab body cap"


def test_opening_a_tab_does_not_add_a_band():
    for tab in ("Requests", "Evidence & RCA", "Connections & audit", "Learn"):
        md = "\n".join(m.value for m in open_page(tab=tab).markdown)
        assert md.count('class="ri-tiles"') == 1 and md.count('class="ri-h2"') == 1
        assert md.count('max-height:164px') == 1 or "max-height:none" in md


def test_holder_and_clock_appear_once():
    at = open_page()
    md = "\n".join(m.value for m in at.markdown)
    clock = re.findall(r"\d+h \d+m left", md)
    assert len(clock) == 1, f"the clock is stated {len(clock)} times: {clock}"
    holder = re.findall(r'<div class="v">(Data Platform|—)</div>', md)
    assert len(holder) == 1, f"the holder is stated {len(holder)} times: {holder}"
    assert "now · held here" in md, "the graph marks the holder without repeating the wait"
