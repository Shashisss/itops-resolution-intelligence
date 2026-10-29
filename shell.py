#!/usr/bin/env python3
"""Application shell — LEFT SIDEBAR navigation (screenshot layout).

Five sections with an icon and a one-line description, exactly as in the proposed structure:
Overview · Incidents · Resolution threads · Analytics · Activity & audit.
Global controls (search, notifications, demo persona, demo menu) stay available."""
import streamlit as st
import viz
import collab

# Four destinations (v99). The incident is its own destination: thread, actions, close gate and
# learn record live on one screen, and Activity & audit is a section at the bottom of it rather than
# a place to go.
NAV_ITEMS = [
    ("Incidents", "▤", "Unified list, filters, severity, ownership, lifecycle."),
    ("Incident", "◉", "The open incident — thread, actions, close gate and learn in one scroll."),
    ("Learn", "◎", "Reusable records — what worked, and incidents with the same signature."),
    ("Analytics", "↗", "MTTR, recurrence, verification outcomes, operational trends."),
    ("Agents", "◇", "One live RCA agent and five design rows — what each may do."),
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
        st.session_state[f"keep_{k}"] = v


def _set_nav(value):
    """Sidebar navigation. Choosing Incidents is also the way back out of an incident workspace —
    without clearing the selection the button looked dead, because the workspace re-rendered.
    Choosing Incident keeps whatever is open; with nothing open it shows the list."""
    if value == "Incident" and not st.session_state.get("open_incident"):
        value = "Incidents"
    st.session_state["nav"] = value
    if value == "Incidents":
        st.session_state.pop("open_incident", None)
        st.session_state["_deep_done"] = True
        try:
            if "inc" in st.query_params:
                del st.query_params["inc"]
        except Exception:
            pass


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


_CTX_SLOT = None


def incident_context(inc_id, verdict, tone, sev, stage, sla):
    """Mirror the open incident into the sidebar.

    Streamlit Cloud serves the app inside an auto-height iframe, so `position: sticky` has no
    scrolling ancestor inside it and cannot pin anything. The sidebar is always visible on every
    host, so the incident identity lives there too."""
    if _CTX_SLOT is None:
        return
    _CTX_SLOT.markdown(
        f'<div class="ri-sbctx"><div class="l">Open incident</div>'
        f'<div class="id">{inc_id}</div>'
        f'<div class="chip" style="background:{tone}1a;color:{tone}">{verdict}</div>'
        f'<div class="meta">{sev} · {stage}</div>'
        f'<div class="meta"><b>{sla}</b></div></div>', unsafe_allow_html=True)


def sidebar(default_role="CSM", stats=None, build=None, demo=False):
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
    if build:
        st.sidebar.caption(f'`{build}`')
    if demo:
        st.sidebar.caption("Demo session · anything you click is discarded on refresh")
    global _CTX_SLOT
    _CTX_SLOT = st.sidebar.empty()
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
    """Global controls: one search that drives the board, plus notifications.

    Every result is actionable. An incident opens its workspace; a service, dataset or pipeline scopes
    the board to that object (the incidents that touch it) and says so with a chip you can clear."""
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
        # Only release a filter this search put there — a deliberate scope must survive.
        if st.session_state.pop("_gs_drives_board", False):
            for k in ("board_q", "keep_board_q"):
                st.session_state[k] = ""
        return

    lo = gs.strip().lower()
    st.session_state["board_q"] = gs.strip()
    st.session_state["keep_board_q"] = gs.strip()
    st.session_state["_gs_drives_board"] = True

    def hit(blob):
        return lo in blob.lower()

    groups = {}
    for i in it_inc:
        if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
            groups.setdefault("Incidents", []).append(
                (f'IT Ops · {i["id"]} · {i["title"]}', ("incident", "IT Ops", i["id"])))
    for i in dop_inc:
        if hit(i["id"] + " " + i["title"] + " " + i["owner_team"]):
            groups.setdefault("Incidents", []).append(
                (f'DataOps · {i["id"]} · {i["title"]}', ("incident", "DataOps", i["id"])))
    for sid, sv in services.items():
        if hit(sid + " " + sv["name"] + " " + sv.get("owner", "")):
            groups.setdefault("Services", []).append(
                (f'{sv["name"]} · {sv["type"]} · {sv.get("owner", "")}', ("service", sv["name"], sid)))
    for did, d in datasets.items():
        if hit(did + " " + d["name"] + " " + d.get("owner_team", "") + " " + d.get("layer", "")):
            groups.setdefault("Datasets", []).append(
                (f'{d["name"]} · {d["layer"]} · {d.get("owner_team", "")}', ("dataset", d["name"], did)))
    for pid, p in pipelines.items():
        if hit(pid + " " + p["name"] + " " + p.get("owner_team", "")):
            groups.setdefault("Pipelines", []).append(
                (f'{p["name"]} · {p.get("owner_team", "")}', ("pipeline", p["name"], pid)))

    total = sum(len(v) for v in groups.values())
    with st.container(border=True):
        if not groups:
            st.markdown(f'**Nothing matches “{gs}”**')
            st.caption("Searched incidents, services, datasets and pipelines. Try an id "
                       "(INC- for IT Ops, DOP- for DataOps), a title fragment, or an owner team.")
            st.button("Clear search", key="gs_clear_empty", on_click=_reset_global_search)
            return
        st.markdown(f'**{total} match{"es" if total != 1 else ""} for “{gs}”**')
        for group, items in groups.items():
            st.caption(f'**{group}** · {len(items)}')
            for label, target in items[:6]:
                kind, name, ident = target
                key = f'gs_{kind}_{"".join(c if c.isalnum() else "_" for c in ident)[:28]}'
                if kind == "incident":
                    st.button(label, key=key, on_click=_goto_incident, args=(name, ident))
                else:
                    st.button(label, key=key, on_click=_scope_to, args=(kind, name))


def _reset_global_search():
    st.session_state["global_search"] = ""
    st.session_state["board_q"] = ""
    st.session_state["keep_board_q"] = ""
    st.session_state["_gs_drives_board"] = False
    st.session_state.pop("scope_note", None)


def _scope_to(kind, name):
    """A service/dataset/pipeline result: show the incidents that touch it, and say which object."""
    st.session_state["global_search"] = ""
    st.session_state["board_q"] = name
    st.session_state["keep_board_q"] = name
    st.session_state["_gs_drives_board"] = False
    st.session_state["scope_note"] = f'{kind.title()}: {name}'
    st.session_state["nav"] = "Incidents"


def _goto_incident(domain, ref):
    import journey
    journey._goto(domain, None, ref)
