#!/usr/bin/env python3
"""Application shell — the ONE navigation model and the global controls.

A persistent sidebar carries global navigation; the top bar carries the global controls
(search · notifications). The demo persona is a global control. There is deliberately no
second navigation axis (no domain switcher + sidebar duplication)."""
import streamlit as st
import viz
import collab
import journey

# Global navigation. "Incidents & resolution threads" is journey.WORKSPACE_NAV — keep in sync.
NAV = ["Overview", journey.WORKSPACE_NAV, "By role", "Data pipelines",
       "Live operations", "Collaboration & activity", "Analytics", "Settings"]

ROLES_UNION = ["CSM", "L1 Engineer", "L2 / L3 Engineer", "Developer", "Incident Manager",
               "Data Engineer", "Data Owner", "Platform Engineer", "Data Consumer"]


def _reset():
    import importlib
    import seed
    importlib.reload(seed)
    st.session_state.clear()


def _notif_list(role):
    notes = collab.notifications_for(role)
    if not notes:
        st.caption("No notifications.")
        return
    for n in notes:
        mark = "•" if n["read"] else "🔵"
        st.markdown(f'{mark} {n["text"]} · _{n["ref_id"]}_')
    if st.button("Mark all read", key="bell_read"):
        collab.mark_all_read(role)
        st.rerun()


def sidebar(default_role):
    """Render the global sidebar; return (nav, role)."""
    viz.brand()
    nav = st.sidebar.radio("Navigation", NAV, key="nav")
    role = st.sidebar.selectbox(
        "👤 Demo persona", ROLES_UNION, key="you_role",
        index=(ROLES_UNION.index(default_role) if default_role in ROLES_UNION else 0))
    st.sidebar.checkbox("⚙️ Demo setting — auto-coordinate on open", key="auto_coord",
                        help="Demo behaviour: coordination (assign + notify) is autonomous under policy; "
                             "production changes still require human approval.")
    with st.sidebar.expander("🎨 Colour legend"):
        viz.legend()
    st.sidebar.divider()
    _reset_control()
    return nav, role


def _reset_control():
    if st.session_state.get("confirm_reset"):
        st.sidebar.warning("Reset wipes all changes (comments, delegations, stages).")
        a, b = st.sidebar.columns(2)
        if a.button("Confirm", key="rc_yes"):
            _reset()
            st.session_state["confirm_reset"] = False
            st.rerun()
        if b.button("Cancel", key="rc_no"):
            st.session_state["confirm_reset"] = False
            st.rerun()
    elif st.sidebar.button("↺ Reset sample data", key="rc"):
        st.session_state["confirm_reset"] = True
        st.rerun()


def topbar(it_inc, dop_inc, role):
    """Global controls: incident search (navigates to the workspace) + notifications."""
    c1, c2 = st.columns([3, 1])
    with c1:
        gs = st.text_input("Search", key="global_search", label_visibility="collapsed",
                           placeholder="🔎 Search incidents, services, owners…")
    with c2:
        unread = collab.unread_count(role)
        if hasattr(st, "popover"):
            with st.popover(f"🔔 {unread}"):
                _notif_list(role)
        else:
            with st.expander(f"🔔 {unread}"):
                _notif_list(role)
    if gs:
        lo = gs.lower()
        hits = [(i["id"], f'IT Ops · {i["title"]} · {i["owner_team"]}', "IT Ops") for i in it_inc
                if lo in (i["id"] + " " + i["title"] + " " + i["owner_team"]).lower()]
        hits += [(i["id"], f'DataOps · {i["title"]} · {i["owner_team"]}', "DataOps") for i in dop_inc
                 if lo in (i["id"] + " " + i["title"] + " " + i["owner_team"]).lower()]
        for ref, lab, dom in hits[:6]:
            st.button(lab, key="gs_" + ref, on_click=journey._goto, args=(dom, None, ref))
        if not hits:
            st.caption("No matches.")
