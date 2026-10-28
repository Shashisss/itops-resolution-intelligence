"""Milestone 1 — end-to-end tests for the incident journey.

Run:  python3 -m pytest tests -q
These drive the real Streamlit app through `AppTest`, so a broken dispatch, a stale session key or a
regression in navigation fails here rather than in a demo.
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402


def start():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    return at


def button_labels(at):
    return [b.label for b in at.button]


def find_button(at, needle):
    for b in at.button:
        if needle in (b.label or ""):
            return b
    raise AssertionError(f"no button matching {needle!r}; have: {button_labels(at)[:20]}")


def test_app_starts_without_exception():
    at = start()
    assert not at.exception, at.exception
    body = " ".join(str(x.value) for x in at.markdown)
    assert "Incidents" in body or any("Incidents" in b for b in button_labels(at))


def test_list_renders_every_incident():
    at = start()
    labels = button_labels(at)
    rows = [l for l in labels if "DOP-1001" in l or "INC-8841" in l]
    assert rows, labels[:20]
    assert len([l for l in labels if "·" in l]) >= 5


def test_open_incident_shows_workspace_and_url():
    at = start()
    find_button(at, "INC-8841").click().run()
    assert not at.exception, at.exception
    text = " ".join(str(x.value) for x in at.markdown)
    assert "Cross-domain" in text and "SLA remaining" in text, "the core strip must be readable first"
    assert "Connections" in text, "the graph panel is part of the incident screen"
    assert at.session_state["open_incident"]["ref"] == "INC-8841"
    assert at.query_params.get("inc") == "INC-8841"


def test_all_incidents_returns_to_list_and_clears_url():
    at = start()
    find_button(at, "INC-8841").click().run()
    assert at.session_state["open_incident"]["ref"] == "INC-8841"
    find_button(at, "All incidents").click().run()
    assert not at.session_state.get("open_incident"), "workspace should be closed"
    assert at.query_params.get("inc") in (None, [], ""), "deep link must be cleared"


def test_filters_survive_opening_and_closing_an_incident():
    at = start()
    at.selectbox(key="board_dom").set_value("DataOps").run()
    assert at.session_state["board_dom"] == "DataOps"
    find_button(at, "DOP-1001").click().run()
    find_button(at, "All incidents").click().run()
    assert at.selectbox(key="board_dom").value == "DataOps", "filter reset when leaving the workspace"
    assert at.session_state.get("board_dom") == "DataOps"


def test_previous_and_next_move_between_incidents():
    at = start()
    find_button(at, "INC-8841").click().run()
    first = at.session_state["open_incident"]["ref"]
    find_button(at, "Next →").click().run()
    second = at.session_state["open_incident"]["ref"]
    assert second != first, "Next did not change the incident"
    find_button(at, "← Previous").click().run()
    assert at.session_state["open_incident"]["ref"] == first


def test_deep_link_opens_the_right_incident_and_only_once():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.query_params["inc"] = "DOP-1001"
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["open_incident"]["ref"] == "DOP-1001"
    find_button(at, "All incidents").click().run()
    assert not at.session_state.get("open_incident"), "deep link reopened the workspace after closing"


def test_entity_result_scopes_the_board_and_reset_clears_it():
    at = start()
    at.text_input(key="global_search").set_value("Payments").run()
    hits = [b for b in at.button if "business_service" in (b.label or "")]
    assert hits, "a service result should be offered for 'Payments'"
    hits[0].click().run()
    assert at.session_state.get("scope_note", "").startswith("Service:"), at.session_state.get("scope_note")
    assert at.session_state.get("board_q"), "the board should be scoped to the object"
    assert at.session_state.get("nav") == "Incidents"
    at.button(key="board_reset").click().run()
    assert not at.session_state.get("scope_note"), "reset should release the scope"


def test_board_search_scopes_the_list_and_reset_releases_it():
    at = start()
    at.text_input(key="board_q").set_value("INC-8841").run()
    labels = [b.label or "" for b in at.button]
    assert any("INC-8841" in l for l in labels), labels[:15]
    assert not any("DOP-1001" in l for l in labels), "the board search must scope the list"
    at.button(key="board_reset").click().run()
    labels = [b.label or "" for b in at.button]
    assert any("DOP-1001" in l for l in labels), "reset must release the search scope"


def test_board_filter_with_no_match_explains_the_empty_result():
    at = start()
    at.text_input(key="board_q").set_value("zzzz-no-such-incident").run()
    text = (" ".join(str(c.value) for c in at.caption)
            + " ".join(str(m.value) for m in at.markdown)
            + " ".join(str(i.value) for i in at.info))
    assert "No incidents match" in text or "Nothing matches" in text
    assert not any("INC-8841" in (b.label or "") for b in at.button)


def test_empty_search_says_so_and_can_be_cleared():
    at = start()
    at.text_input(key="global_search").set_value("zzzz-no-such-thing").run()
    text = " ".join(str(c.value) for c in at.caption) + " ".join(str(m.value) for m in at.markdown)
    assert "Nothing matches" in text or "No match" in text
    at.button(key="gs_clear_empty").click().run()
    assert not at.session_state.get("global_search")


def test_sidebar_incidents_returns_from_a_workspace():
    at = start()
    find_button(at, "INC-8841").click().run()
    assert at.session_state["open_incident"]["ref"] == "INC-8841"
    at.button(key="nav_Incidents").click().run()
    assert not at.session_state.get("open_incident"), "sidebar Incidents must leave the workspace"
    assert at.query_params.get("inc") in (None, [], ""), "and clear the deep link"
    assert any("DOP-1001" in (b.label or "") for b in at.button), "the list should be rendered"
