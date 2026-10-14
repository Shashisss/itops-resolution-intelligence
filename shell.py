#!/usr/bin/env python3
"""Application shell — a TOP menu + global controls. No left sidebar.

One navigation model (a horizontal top menu), one role control (the Demo persona in the top
bar — there is no second persona selector anywhere), and the global controls (search ·
notifications · demo settings) on one row."""
import streamlit as st
import viz
import collab
import journey

# Top menu. journey.WORKSPACE_NAV ("Incidents") opens the board/workspace — keep in sync.
NAV = ["Overview", journey.WORKSPACE_NAV, "By role", "Pipelines", "Live ops",
       "Collaboration", "Analytics", "Settings"]

ROLES_UNION = ["CSM", "L1 Engineer", "L2 / L3 Engineer", "Developer", "Incident Manager",
               "Data Engineer", "Data Owner", "Platform Engineer", "Data Consumer"]


def _reset():
    import importlib
    import seed
    importlib.reload(seed)
    st.session_state.clear()


def _reset_control():
    if st.session_state.get("confirm_reset"):
        st.warning("Reset wipes all changes (comments, delegations, stages).")
        a, b = st.columns(2)
        if a.button("Confirm reset", key="rc_yes"):
            _reset()
            st.session_state["confirm_reset"] = False
            st.rerun()
        if b.button("Cancel", key="rc_no"):
            st.session_state["confirm_reset"] = False
            st.rerun()
    elif st.button("↺ Reset sample data", key="rc"):
        st.session_state["confirm_reset"] = True
        st.rerun()


def _bell(role):
    unread = collab.unread_count(role)
    notes = collab.notifications_for(role)
    label = f"🔔 {unread}"
    box = st.popover(label) if hasattr(st, "popover") else st.expander(label)
    with box:
        if not notes:
            st.caption("No notifications.")
        for n in notes:
            mark = "•" if n["read"] else "🔵"
            st.markdown(f'{mark} {n["text"]} · _{n["ref_id"]}_')
        if notes and st.button("Mark all read", key="bell_read"):
            collab.mark_all_read(role)
            st.rerun()


def _demo_menu():
    box = st.popover("⚙️ Demo") if hasattr(st, "popover") else st.expander("⚙️ Demo")
    with box:
        st.checkbox("Auto-coordinate on open", key="auto_coord",
                    help="Coordination (assign + notify) is autonomous under policy; production changes "
                         "still require human approval.")
        st.markdown("**Colour legend**")
        viz.legend()
        st.divider()
        _reset_control()


def topbar(it_inc, dop_inc):
    """Render the top menu + global controls. Returns (nav, role)."""
    st.markdown('<div class="ri-topbrand">Resolution Intelligence '
                '<span>· unified operations workspace</span></div>', unsafe_allow_html=True)
    nav = st.radio("Navigation", NAV, horizontal=True, key="nav", label_visibility="collapsed")

    c1, c2, c3, c4 = st.columns([3.4, 1.6, 0.9, 0.9])
    with c1:
        gs = st.text_input("Search", key="global_search", label_visibility="collapsed",
                           placeholder="🔎 Search incidents, services, owners…")
    with c2:
        role = st.selectbox("👤 Demo persona", ROLES_UNION, key="you_role")
    with c3:
        _bell(role)
    with c4:
        _demo_menu()

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
    return nav, role
