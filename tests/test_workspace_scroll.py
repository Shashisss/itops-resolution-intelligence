"""Workspace scrolling — one scroll surface, a pinned identity bar, actions that jump to their section.

v93 put the thread and the guided walkthrough inside a fixed-height box (clamp 300–560px) so the
identity bar could stay on screen inside Streamlit Cloud's auto-height iframe. On a laptop that made
the walkthrough a keyhole with its own scrollbar. v94 removes the nested scroll: the content flows in
the app's single scroll surface, the bar pins to the top of it, and an action lands the page on the
section it opened.
"""
import os
import pathlib
import re
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


_PANEL_RULE = re.compile(r"\.st-key-ws_panel_[^{]*\{([^}]*)\}")


def panel_declarations(css):
    """Declarations inside every rule that targets the thread panel.

    The guard is about the panel, not about the whole stylesheet: a clamp() on a font-size elsewhere
    is legitimate, a clamped height on this container is the nested scroll that v94 removed."""
    return [m.group(1) for m in _PANEL_RULE.finditer(css)]


def panel_height_violations(css):
    """The bug this test exists to catch: any height cap on the thread panel.

    `height: auto` / `max-height: none` are the fix and pass; a clamp, a px cap or a percentage is
    a nested scroll and fails. Any clamp() in a panel declaration fails too."""
    bad = []
    allowed = {"auto", "none", "unset", "initial", "inherit"}
    for decls in panel_declarations(css):
        for decl in decls.split(";"):
            prop, _, value = decl.partition(":")
            prop = prop.strip().lower()
            value = value.replace("!important", "").strip().lower()
            if "clamp(" in value:
                bad.append(f"{prop}: {value}")
            elif prop in ("height", "max-height") and value not in allowed:
                bad.append(f"{prop}: {value}")
    return bad


def test_thread_panel_is_not_height_clamped():
    at = open_incident()
    css = all_markdown(at)
    assert "st-key-ws_panel_" in css, "the thread container should still be addressed by CSS"
    assert panel_declarations(css), "the panel rule must actually be rendered for this guard to mean anything"
    assert panel_height_violations(css) == [], (
        "the panel must not cap its height — that is the nested scroll that turned the walkthrough "
        f"into a keyhole: {panel_height_violations(css)}")
    assert "scroll-margin-top" in css, "jump targets need a margin so the sticky bar cannot cover them"


def test_the_panel_guard_still_catches_a_clamped_height():
    """The narrowed guard must still fail on the bug it was written for — it is not a weaker test."""
    assert panel_height_violations(
        ".st-key-ws_panel_INC-1 { flex: 0 0 auto; height: clamp(300px, 50vh, 560px) !important; }")
    assert panel_height_violations(".st-key-ws_panel_INC-1 { max-height: 560px !important; }")
    assert panel_height_violations(".st-key-ws_panel_INC-1 { height: 70vh !important; }")
    assert panel_height_violations(
        ".st-key-ws_panel_INC-1 { height: auto !important; max-height: none !important; "
        "overflow: visible !important; }") == [], "the real fix must pass"


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


def test_dataops_workspace_is_the_same_one_scroll_with_the_same_anchors():
    """v99 removed the lens switch and the step control: both domains render every stage as an
    anchored section in one scroll, and a stage action still lands on its own section."""
    at = open_incident("DOP-1001")
    assert not at.exception, at.exception
    text = all_markdown(at)
    assert "Connections" in text, "the incident screen carries the connections section"
    assert "Close & Learn" in text, "the phase name appears in the stage headers"
    assert not any(r.key == "ws_mode_DOP-1001" for r in at.radio), "the lens switch is gone"
    at.session_state["_scroll_anchor"] = "dop_step_DOP-1001_anchor_Act"
    at.run()
    assert not at.exception, at.exception
