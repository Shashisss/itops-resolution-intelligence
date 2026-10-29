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


def test_incident_opens_with_only_the_current_stage_expanded():
    at = open_incident()
    current = journey.lifecycle_stage({"stage": "Diagnosed", "status": "open"})
    assert at.session_state["open_INC-8841"] == f"stage:{current}"
    assert "Detection — what fired and when" not in text(at), "Detect must be folded"
    assert "hypotheses" in text(at).lower(), "the current stage's content is the one shown"
    labelled = headers(at)
    assert sum(1 for h in labelled if h.startswith("▾")) == 1, labelled
    assert sum(1 for h in labelled if h.startswith("▸")) >= 10, "stages + the folded sections"


def test_opening_one_section_closes_the_other():
    at = open_incident()
    press(at, "Detect")
    assert at.session_state["open_INC-8841"] == "stage:Detect"
    assert "Detection — what fired and when" in text(at), "Detect is now open"
    assert "hypotheses" not in text(at).lower(), "opening Detect closed Correlate"
    press(at, "Close")
    assert at.session_state["open_INC-8841"] == "stage:Close"
    assert "Detection — what fired and when" not in text(at), "again only one section is open"


def test_deep_links_open_exactly_one_section():
    at = open_incident(step="Act")
    assert at.session_state["open_INC-8841"] == "stage:Act"
    at = open_incident(expand="connections")
    assert at.session_state["open_INC-8841"] == "connections"
    assert "Caused by" in text(at) and "Evidenced by" in text(at)
    at = open_incident(expand="activity")
    assert at.session_state["open_INC-8841"] == "activity"


def test_collapsed_headers_state_blocked_overdue_and_unverified():
    at = open_incident()
    labelled = " || ".join(headers(at))
    assert "Act  ·  OVERDUE" in labelled, "an overdue request shows in the Act header"
    assert "Verify  ·  UNVERIFIED" in labelled, "an unverified recovery shows in the Verify header"
    assert "Close  ·  BLOCKED" in labelled, "a blocked close shows in the Close header"
    for stage in journey.LIFECYCLE:
        assert f"{stage}  ·" in labelled, f"{stage} header carries its own line"
    assert "Connections  ·" in labelled and "Activity & audit  ·" in labelled


def test_list_rows_answer_the_queue_questions():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
    rows = [b.label for b in at.button if "INC-8841" in (b.label or "") and "\n" in (b.label or "")]
    assert rows, "the list row is a two-line button"
    line = rows[0].split("\n")[-1]
    assert "holds" in line, line
    assert "left" in line or "closed" in line, line
    assert "cross-domain" in line or "single-domain" in line, line
    assert "next:" in line, line


def test_row_opens_the_drawer_then_the_incident():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
    for b in at.button:
        if "INC-8841" in (b.label or ""):
            b.click().run()
            break
    assert not at.exception, [e.value for e in at.exception]
    assert not at.session_state.get("open_incident"), "selecting a row must not open the workspace"
    assert at.session_state["board_preview"]["ref"] == "INC-8841"
    assert any("Open incident" == (b.label or "") for b in at.button)
    body = " ".join(str(m.value) for m in at.markdown)
    assert "Data Platform" in body and "holds" in text(at).lower() + body.lower()
    at.button(key="drawer_open_INC-8841").click().run()
    assert at.session_state["open_incident"]["ref"] == "INC-8841"
