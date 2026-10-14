#!/usr/bin/env python3
"""Application shell — a TOP menu + global controls. No left sidebar.

One navigation model (a horizontal top menu), one role control (the Demo persona in the top
bar — there is no second persona selector anywhere), and the global controls (search ·
notifications · demo settings) on one row."""
import streamlit as st
import viz
import collab
import journey

# Top menu — four primary destinations. journey.WORKSPACE_NAV ("Incidents") opens the
# board/workspace and carries the role lens. Keep in sync.
NAV = [journey.WORKSPACE_NAV, "Analytics"]

ROLES_UNION = ["CIO", "CSM", "Incident Manager", "Service Desk", "L1 Engineer",
               "L2 / L3 Engineer", "Developer", "Data Engineer", "Data Owner",
               "Platform Engineer", "Data Consumer"]


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
        st.caption("Settings — connectors (ServiceNow, Jira), stage OLA targets, policy and access (RBAC) "
                   "are production concerns, not simulated in this prototype.")
        _reset_control()


def topbar(it_inc, dop_inc, services, datasets, pipelines):
    """Render the top menu + global controls. Returns (nav, role)."""
    st.markdown('<div class="ri-topbrand">Resolution Intelligence '
                '<span>· unified operations workspace</span></div>', unsafe_allow_html=True)
    nav = st.radio("Navigation", NAV, horizontal=True, key="nav", label_visibility="collapsed")

    c1, c2, c3, c4 = st.columns([3.4, 1.6, 0.9, 0.9])
    with c1:
        gs = st.text_input("Search", key="global_search", label_visibility="collapsed",
                           placeholder="🔎 Search incidents, services, datasets, pipelines, owners…")
    with c2:
        role = st.selectbox("👤 Demo persona", ROLES_UNION, key="you_role")
    with c3:
        _bell(role)
    with c4:
        _demo_menu()

    if gs:
        lo = gs.lower()

        def hit(blob):
            return lo in blob.lower()

        groups = {}
        for i in it_inc:
            if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
                groups.setdefault("Incidents", []).append(
                    (f'IT Ops · {i["id"]} · {i["title"]}',
                     ("goto", "IT Ops", i["id"])))
        for i in dop_inc:
            if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
                groups.setdefault("Incidents", []).append(
                    (f'DataOps · {i["id"]} · {i["title"]}',
                     ("goto", "DataOps", i["id"])))
        for sid, s in services.items():
            if hit(sid + " " + s["name"] + " " + s.get("owner", "")):
                groups.setdefault("Services", []).append(
                    (f'{s["name"]} · {s["type"]} · {s["owner"]}', ("ops",)))
        for did, d in datasets.items():
            if hit(did + " " + d["name"] + " " + d.get("owner_team", "") + " " + d.get("layer", "")):
                groups.setdefault("Datasets", []).append(
                    (f'{d["name"]} · {d["layer"]} · {d.get("owner_team","")}', ("ops",)))
        for pid, p in pipelines.items():
            if hit(pid + " " + p["name"] + " " + p.get("owner_team", "")):
                groups.setdefault("Pipelines", []).append(
                    (f'{p["name"]} · {p.get("owner_team","")}', ("ops",)))
        if not groups:
            st.caption("No matches.")
        for group, items in groups.items():
            st.caption(f'**{group}** · {len(items)}')
            for label, target in items[:5]:
                key = f'gs_{group}_{abs(hash(label)) % 10**8}'
                if target[0] == "goto":
                    st.button(label, key=key, on_click=journey._goto, args=(target[1], None, target[2]))
                else:
                    st.button(label + "  → Operations", key=key, on_click=journey._nav_to,
                              args=("Operations",))
    return nav, role
