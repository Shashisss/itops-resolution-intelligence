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

# Personas are a lens, not decoration: each one sets the view it opens on and states whether it may
# execute a production change. Execution stays human-approved for every role; this only scopes it.
PERSONA_MATRIX = {
    "CIO": dict(scope="Portfolio — every domain, every team", board=dict(board_dom="All", board_status="All"),
                exec=True, note="Approves policy and high-risk execution"),
    "CSM": dict(scope="Customer impact — open incidents touching a business service",
                board=dict(board_dom="All", board_status="Open"), exec=True,
                note="Owns customer comms, not remediation"),
    "Incident Manager": dict(scope="Major incidents — coordination and approval",
                             board=dict(board_dom="All", board_status="Open"), exec=True,
                             note="Approves execution, owns the bridge"),
    "Service Desk": dict(scope="Queue — everything open, by priority",
                         board=dict(board_dom="All", board_status="Open", board_pri="All"), exec=False,
                         note="Triage and routing only"),
    "L1 Engineer": dict(scope="Your queue — open incidents in either domain",
                        board=dict(board_dom="All", board_status="Open"), exec=False,
                        note="Diagnose and escalate; execution needs approval"),
    "L2 / L3 Engineer": dict(scope="Deep investigation — open incidents",
                             board=dict(board_dom="All", board_status="Open"), exec=True,
                             note="Executes approved remediation"),
    "Developer": dict(scope="Change-driven incidents — IT Ops",
                      board=dict(board_dom="IT Ops", board_status="All"), exec=True,
                      note="Owns the deploy that caused it"),
    "Data Engineer": dict(scope="Pipelines and freshness — DataOps",
                          board=dict(board_dom="DataOps", board_status="All"), exec=True,
                          note="Repairs pipelines, replays batches"),
    "Data Owner": dict(scope="Data products and contracts — DataOps",
                       board=dict(board_dom="DataOps", board_status="All"), exec=True,
                       note="Approves schema/contract changes"),
    "Platform Engineer": dict(scope="Shared platform and services — IT Ops",
                              board=dict(board_dom="IT Ops", board_status="All"), exec=True,
                              note="Owns service reliability"),
    "Data Consumer": dict(scope="Downstream impact — what is stale right now",
                          board=dict(board_dom="DataOps", board_status="All"), exec=False,
                          note="Read-only: sees freshness and impact, cannot act"),
}


def persona(role):
    return PERSONA_MATRIX.get(role, dict(scope="All incidents", board={}, exec=False,
                                         note="Read-only"))


def can_execute(role):
    return bool(persona(role)["exec"])


def _apply_persona():
    """Switching persona applies that persona's default board view immediately."""
    spec = persona(st.session_state.get("you_role"))
    for k, v in spec["board"].items():
        st.session_state[k] = v


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


def sidebar(default_role="CSM", stats=None):
    """Left sidebar: brand, live counts, sections, persona, demo menu."""
    st.sidebar.markdown(
        '<div class="ri-sidebrand">Resolution Intelligence<br>'
        '<span>Unified IT Ops + DataOps</span></div>', unsafe_allow_html=True)
    if stats:
        st.sidebar.markdown(
            f'<div class="ri-sidecounts"><span><b>{stats["open"]}</b> open</span>'
            f'<span><b>{stats["cross"]}</b> cross-domain</span>'
            f'<span><b>{stats["total"]}</b> total</span></div>', unsafe_allow_html=True)
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
    role = st.sidebar.selectbox("Demo persona", ROLES_UNION, key="you_role",
                                on_change=_apply_persona)
    _p = persona(role)
    st.sidebar.caption(f'**{_p["scope"]}** · {_p["note"]}'
                       + ("" if _p["exec"] else " · read-only"))
    with st.sidebar:
        _demo_menu()
    return nav, role


def topbar(it_inc, dop_inc, services, datasets, pipelines, role):
    """Global controls: one search that drives the board, plus notifications."""
    c1, c2 = st.columns([4.6, 1], vertical_alignment="bottom")
    with c1:
        gs = st.text_input("Search everything", key="global_search",
                           placeholder="incident id, title, owner, service, dataset or pipeline — then Enter")
    with c2:
        unread = collab.unread_count(role)
        if st.button(f"Notifications · {unread}", key="notif_toggle", width="stretch"):
            st.session_state["show_notifs"] = not st.session_state.get("show_notifs", False)
    if st.session_state.get("show_notifs"):
        with st.container(border=True):
            _notif_list(role)

    if not gs:
        # A cleared search releases the board; it must never leave it filtered invisibly.
        if st.session_state.get("board_q"):
            st.session_state["board_q"] = ""
        return

    lo = gs.strip().lower()
    # One behaviour: typing in the global search IS the board filter.
    st.session_state["board_q"] = gs.strip()

    def hit(blob):
        return lo in blob.lower()

    groups = {}
    for i in it_inc:
        if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
            groups.setdefault("Incidents", []).append((f'IT Ops · {i["id"]} · {i["title"]}', ("IT Ops", i["id"])))
    for i in dop_inc:
        if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
            groups.setdefault("Incidents", []).append((f'DataOps · {i["id"]} · {i["title"]}', ("DataOps", i["id"])))
    for sid, s in services.items():
        if hit(sid + " " + s["name"] + " " + s.get("owner", "")):
            groups.setdefault("Services", []).append((f'{s["name"]} · {s["type"]} · {s["owner"]}', None))
    for did, d in datasets.items():
        if hit(did + " " + d["name"] + " " + d.get("owner_team", "") + " " + d.get("layer", "")):
            groups.setdefault("Datasets", []).append((f'{d["name"]} · {d["layer"]} · {d.get("owner_team", "")}', None))
    for pid, p in pipelines.items():
        if hit(pid + " " + p["name"] + " " + p.get("owner_team", "")):
            groups.setdefault("Pipelines", []).append((f'{p["name"]} · {p.get("owner_team", "")}', None))

    total = sum(len(v) for v in groups.values())
    with st.container(border=True):
        if not groups:
            st.markdown(f'**No match for “{gs}”** — nothing in incidents, services, datasets or pipelines.')
            st.caption("Check the id prefix (INC- for IT Ops, DOP- for DataOps) or search an owner team.")
            return
        st.markdown(f'**{total} match{"es" if total != 1 else ""} for “{gs}”** · the incident board below is '
                    f'filtered to the same query')
        for group, items in groups.items():
            st.caption(f'**{group}** · {len(items)}')
            for label, target in items[:6]:
                if target:
                    st.button(label, key=f'gs_{group}_{abs(hash(label)) % 10**8}',
                              on_click=_goto_incident, args=(target[0], target[1]))
                else:
                    st.markdown(f'- {label}')


def _goto_incident(domain, ref):
    import journey
    journey._goto(domain, None, ref)
