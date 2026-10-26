#!/usr/bin/env python3
"""Application shell — LEFT SIDEBAR navigation (screenshot layout).

Five sections with an icon and a one-line description, exactly as in the proposed structure:
Overview · Incidents · Resolution threads · Analytics · Activity & audit.
Global controls (search, notifications, demo persona, demo menu) stay available."""
import streamlit as st
import viz
import collab

NAV_ITEMS = [
    ("Incidents", "▤", "Unified list, filters, severity, ownership, lifecycle."),
    ("Analytics", "↗", "MTTR, recurrence, verification outcomes, operational trends."),
    ("Activity & audit", "◷", "Actions, approvals, handoffs, verification records."),
]
NAV = [n for n, _, _ in NAV_ITEMS]

ROLES_UNION = ["CIO", "CSM", "Incident Manager", "Service Desk", "L1 Engineer",
               "L2 / L3 Engineer", "Developer", "Data Engineer", "Data Owner",
               "Platform Engineer", "Data Consumer"]


def _set_nav(value):
    st.session_state["nav"] = value


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


def sidebar(default_role="CSM"):
    """Left sidebar: brand, five sections (icon + description), persona, demo menu."""
    st.sidebar.markdown(
        '<div class="ri-sidebrand">Resolution Intelligence<br>'
        '<span>Unified IT Ops + DataOps</span></div>', unsafe_allow_html=True)
    nav = st.session_state.get("nav", "Incidents")
    if nav not in NAV:
        nav = "Incidents"
    st.session_state["nav"] = nav
    for label, icon, desc in NAV_ITEMS:
        st.sidebar.button(f"{icon}  {label}", key=f"nav_{label}", width="stretch",
                          type=("primary" if nav == label else "secondary"),
                          on_click=_set_nav, args=(label,), help=desc)
        if nav == label:
            st.sidebar.caption(desc)
    st.sidebar.divider()
    role = st.sidebar.selectbox("👤 Demo persona", ROLES_UNION, key="you_role")
    with st.sidebar:
        _demo_menu()
    return nav, role


def topbar(it_inc, dop_inc, services, datasets, pipelines, role):
    """Global controls: search (navigates to incidents) + notifications."""
    c1, c2 = st.columns([4.6, 1])
    with c1:
        gs = st.text_input("Search", key="global_search", label_visibility="collapsed",
                           placeholder="🔎 Search incidents, services, datasets, pipelines, owners…")
    with c2:
        unread = collab.unread_count(role)
        box = st.popover(f"🔔 {unread}") if hasattr(st, "popover") else st.expander(f"🔔 {unread}")
        with box:
            _notif_list(role)

    if gs:
        import journey
        lo = gs.lower()

        def hit(blob):
            return lo in blob.lower()

        groups = {}
        for i in it_inc:
            if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
                groups.setdefault("Incidents", []).append(
                    (f'IT Ops · {i["id"]} · {i["title"]}', ("IT Ops", i["id"])))
        for i in dop_inc:
            if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
                groups.setdefault("Incidents", []).append(
                    (f'DataOps · {i["id"]} · {i["title"]}', ("DataOps", i["id"])))
        for sid, s in services.items():
            if hit(sid + " " + s["name"] + " " + s.get("owner", "")):
                groups.setdefault("Services", []).append((f'{s["name"]} · {s["type"]} · {s["owner"]}', None))
        for did, d in datasets.items():
            if hit(did + " " + d["name"] + " " + d.get("owner_team", "") + " " + d.get("layer", "")):
                groups.setdefault("Datasets", []).append(
                    (f'{d["name"]} · {d["layer"]} · {d.get("owner_team","")}', None))
        for pid, p in pipelines.items():
            if hit(pid + " " + p["name"] + " " + p.get("owner_team", "")):
                groups.setdefault("Pipelines", []).append((f'{p["name"]} · {p.get("owner_team","")}', None))
        if not groups:
            st.caption("No matches.")
        for group, items in groups.items():
            st.caption(f'**{group}** · {len(items)}')
            for label, target in items[:5]:
                if target:
                    st.button(label, key=f'gs_{group}_{abs(hash(label)) % 10**8}',
                              on_click=journey._goto, args=(target[0], None, target[1]))
                else:
                    st.markdown(f'- {label}')
