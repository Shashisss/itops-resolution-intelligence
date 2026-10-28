"""Workspace scrolling — one scroll surface, a pinned identity bar, actions that jump to their section.

v93 put the thread and the guided walkthrough inside a fixed-height box (clamp 300–560px) so the
identity bar could stay on screen inside Streamlit Cloud's auto-height iframe. On a laptop that made
the walkthrough a keyhole with its own scrollbar. v94 removes the nested scroll: the content flows in
the app's single scroll surface, the bar pins to the top of it, and an action lands the page on the
section it opened.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402


def start():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    return at


def find_button(at, needle):
    for b in at.button:
        if needle in (b.label or ""):
            return b
    raise AssertionError(f"no button matching {needle!r}; have: {[b.label for b in at.button][:20]}")


def open_incident(ref="INC-8841"):
    at = start()
    find_button(at, ref).click().run()
    return at


def all_markdown(at):
    return " ".join(str(x.value) for x in at.markdown)


def test_thread_panel_is_not_height_clamped():
    at = open_incident()
    css = all_markdown(at)
    assert "st-key-ws_panel_" in css, "the thread container should still be addressed by CSS"
    assert "clamp(" not in css, "the panel must not have a clamped height — that is the nested scroll"
    assert "max-height: 560px" not in css, "the old fixed cap is what turned the walkthrough into a keyhole"
    assert "scroll-margin-top" in css, "jump targets need a margin so the sticky bar cannot cover them"


def test_primary_action_opens_the_matching_guided_step():
    at = open_incident()
    find_button(at, "Confirm cause").click().run()
    assert not at.exception, at.exception
    assert at.session_state["ws_mode_INC-8841"] == "Act & verify (guided)"
    assert at.session_state["it_step_INC-8841"] == "Correlate", "Confirm cause should land on Correlate"
    assert "Root cause" in all_markdown(at) or "Root cause" in " ".join(
        str(x.value) for x in at.expander), "the hypothesis section is what the action claims to open"


def test_guided_walkthrough_step_is_remembered_per_incident():
    at = open_incident()
    find_button(at, "Confirm cause").click().run()
    at.session_state["it_step_INC-8841"] = "Verify"
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["it_step_INC-8841"] == "Verify"


def test_dataops_workspace_uses_the_same_anchored_wizard():
    at = open_incident("DOP-1001")
    assert not at.exception, at.exception
    at.radio(key="ws_mode_DOP-1001").set_value("Act & verify (guided)").run()
    assert not at.exception, at.exception
    assert at.session_state["dop_step_DOP-1001"] in ("Detect", "Correlate", "Coordinate",
                                                    "Act", "Verify", "Close")
