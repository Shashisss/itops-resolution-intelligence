"""Progressive disclosure (v106) — the page shows what matters and folds the rest.

Two behaviours are load-bearing: the incident opens with only the current stage's content, and
opening one section closes the other (one accordion, predictable height). The collapsed headers must
still tell the truth — a blocked close or an unverified recovery is stated in the header, not only
after the click.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import journey  # noqa: E402
import story  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402


def open_incident(ref="INC-8841", **params):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.query_params["inc"] = ref
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def headers(at):
    return [b.label for b in at.button if (b.label or "").startswith(("▸", "▾"))]


def press(at, needle):
    for b in at.button:
        if (b.label or "").startswith(("▸", "▾")) and needle in b.label:
            b.click().run()
            assert not at.exception, [e.value for e in at.exception]
            return at
    raise AssertionError(f"no section header matching {needle!r}: {headers(at)}")


def text(at):
    return " ".join([str(m.value) for m in at.markdown] + [str(c.value) for c in at.caption]
                    + [str(b.label) for b in at.button])


TABS = ["Timeline", "Requests", "Evidence & RCA", "Connections & audit", "Act & verify", "Learn"]


def tab_buttons(at):
    return [(b.label.split(" · ")[0], b.label) for b in at.button
            if (b.label or "").split(" · ")[0] in TABS]


def test_incident_opens_on_one_tab_only():
    at = open_incident()
    assert at.session_state["tab_INC-8841"] == "Timeline", "the default tab is Timeline"
    assert len(tab_buttons(at)) == 6, tab_buttons(at)
    assert "Operational timeline" in text(at) or "timeline" in text(at).lower()
    assert "Root cause — ranked hypotheses" not in text(at), "other tabs are not rendered"


def test_opening_one_tab_closes_the_other():
    at = open_incident()
    press_tab(at, "Learn")
    assert at.session_state["tab_INC-8841"] == "Learn"
    assert "Learn — capture what worked" in text(at)
    assert "Operational timeline" not in text(at), "opening Learn closed Timeline"
    press_tab(at, "Requests")
    assert at.session_state["tab_INC-8841"] == "Requests"
    assert "Learn — capture what worked" not in text(at)


def press_tab(at, name):
    for b in at.button:
        if (b.label or "").split(" · ")[0] == name:
            b.click().run()
            assert not at.exception, [e.value for e in at.exception]
            return at
    raise AssertionError(f"no tab {name!r}: {[b.label for b in at.button][:20]}")


def test_deep_links_select_a_tab_and_a_stage():
    at = open_incident(tab="Connections & audit")
    assert at.session_state["tab_INC-8841"] == "Connections & audit"
    assert "Caused by" in text(at)
    at = open_incident(step="Close")
    assert at.session_state["tab_INC-8841"] == "Act & verify"
    assert at.session_state["act_stage_INC-8841"] == "Close"
    assert "Closure" in text(at)


def test_tab_headers_carry_counts_and_critical_state():
    at = open_incident()
    labels = " || ".join(l for _, l in tab_buttons(at))
    assert "Requests · 2 open · 1 OVERDUE" in labels, labels
    assert "Act & verify · BLOCKED" in labels, labels
    assert "Learn · draft, not saved" in labels, labels
    assert "Connections & audit ·" in labels and "records" in labels, labels
    assert "Timeline · " in labels and "events" in labels, labels


def test_act_and_verify_holds_every_stage_action():
    at = open_incident(tab="Act & verify")
    labels = [b.label for b in at.button]
    for need in ("Confirm cause", "Apply remediation", "Run verification", "Close"):
        assert need in labels, f"{need} must be reachable in Act & verify: {labels}"


def test_the_tab_body_is_capped_so_the_page_cannot_grow():
    """The height cap is a CSS contract: every tab body is capped, and only Act & verify lifts it.

    The pixel measurement (768px at 1366×768, no scrollbar) is taken in the browser; this keeps the
    structure that produces it from regressing silently."""
    at = open_incident()
    css = " ".join(str(m.value) for m in at.markdown)
    assert 'div[class*="st-key-tabbody_"]{max-height:224px;overflow:hidden}' in css
    assert len([b for b in at.button if (b.label or "").startswith("Show all")]) == 1
    at2 = open_incident(tab="Act & verify")
    css2 = " ".join(str(m.value) for m in at2.markdown)
    assert "max-height:none;overflow:visible" in css2, "Act & verify is the uncapped tab"
