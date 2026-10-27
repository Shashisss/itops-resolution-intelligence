#!/usr/bin/env python3
"""Resolution Intelligence — Streamlit POC.
One governed platform across IT Ops and DataOps.
Unified shell · one incident workspace · one lifecycle · one status vocabulary.
Deterministic graph + rule-based reasoning. SAMPLE DATA · SIMULATED ACTIONS."""
import os
import datetime as dt
import importlib
import pandas as pd
import streamlit as st
import engine as E
import personas
import dataops_engine as DE
import dataops_views as DV
import command_center
import viz
import journey
import collab
import shell
import workspace
import realtime


def _refresh_modules():
    """Reload our own modules so the running app always matches app.py.

    Streamlit Cloud can hot-reload app.py while leaving imported sibling modules cached at an
    older build — which caused AttributeError (missing helpers) and TypeError (missing params,
    e.g. board_card(linked=…)) on newly added code. importlib.reload mutates the module object in
    place, so every importer sees the refreshed definitions. Doing this every run is cheap (the
    modules only define functions) and removes the whole class of stale-module failures."""
    for _m in (viz, journey, collab, E, DE, personas, DV, workspace, command_center, shell):
        try:
            importlib.reload(_m)
        except Exception:
            pass


_refresh_modules()

VERDICT_OPTIONS = ["Investigating", "Mitigated", "Verified", "Recovery failed", "Inconclusive"]


def _needs_seed():
    import sqlite3
    if not os.path.exists("data/ops.db"):
        return True
    try:
        con = sqlite3.connect("data/ops.db")
        required = ("tickets", "kpis", "incidents", "pipelines", "dop_incidents", "timeline",
                    "correlations", "service_data", "live_events", "comments", "delegations", "notifications",
                    "olas", "stage_olas")
        for t in required:
            con.execute(f"SELECT 1 FROM {t} LIMIT 1")
        v = con.execute("SELECT value FROM meta WHERE key='seed_version'").fetchone()
        con.close()
        return not (v and v[0] == "v75")
    except Exception:
        return True


if _needs_seed():
    import seed  # noqa: F401

import clock  # noqa: E402
import build  # noqa: E402
import store  # noqa: E402
build.info.cache_clear()   # a hot reload swaps app.py without restarting the process
clock.align()

# Every browser session gets its own copy of the demo database: actions, verifications and closures
# are real inside the session and gone after a refresh. Set RI_DEMO_MODE=0 to persist.
_DB_PATH = store.db()
for _mod in (E, DE, journey, collab, realtime):
    _mod.DB = _DB_PATH
_DEMO_SESSION = store.is_demo()

st.set_page_config(page_title="Resolution Intelligence — POC", page_icon="assets/icon.png",
                   layout="wide")
viz.inject_css()

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

_sv, _ed, _it_inc, _ch, _me, _G = E.load()
_dop_data = DE.load()
_dop_inc = _dop_data["incidents"]

# ---- deep link: ?inc=<ID> opens that incident directly (a thread you can paste into a bridge call)
_deep_ref = str(st.query_params.get("inc") or "").strip()
if _deep_ref and not st.session_state.get("_deep_done") and not st.session_state.get("open_incident"):
    # Consume the deep link once per session. Without the flag, closing the workspace would be
    # undone on the next rerun because the ?inc= parameter is still in the address bar.
    st.session_state["_deep_done"] = True
    _deep_dom = "DataOps" if _deep_ref.upper().startswith("DOP") else "IT Ops"
    _exists = any(i["id"] == _deep_ref for i in (_it_inc if _deep_dom == "IT Ops" else _dop_inc))
    if _exists:
        st.session_state["open_incident"] = {"domain": _deep_dom, "ref": _deep_ref}
        st.session_state["nav"] = "Incidents"
# ---- left sidebar navigation (five sections) ----
_open_n = sum(1 for i in list(_it_inc) + list(_dop_inc) if i.get("status") == "open")
_cross_n = sum(1 for i in _it_inc if journey.correlation_for(i["id"]))
nav, you_role = shell.sidebar("CSM", stats={"open": _open_n, "cross": _cross_n,
                                           "total": len(_it_inc) + len(_dop_inc)},
                              build=build.label(), demo=_DEMO_SESSION)
# ---- global controls ----
shell.topbar(_it_inc, _dop_inc, _sv, _dop_data["datasets"], _dop_data["pipelines"], you_role)


def _it_ctx():
    services, edges, incidents, changes, metrics, G = E.load()
    return dict(services=services, edges=edges, incidents=incidents, changes=changes, metrics=metrics,
                tickets=E.load_tickets(), kpis=E.load_kpis(), G=G)


def _find_it(ref):
    return next((i for i in _it_inc if i["id"] == ref), None)


def _find_dop(ref):
    return next((i for i in _dop_inc if i["id"] == ref), None)


def _sla_risk(i):
    target = personas.SLA_HOURS.get(i["priority"], 8)
    try:
        elapsed = (dt.datetime.now() - dt.datetime.fromisoformat(i["created_at"])).total_seconds() / 3600
    except Exception:
        elapsed = 0.0
    return (target - elapsed) < target * 0.5


def _sla_txt(i):
    target = personas.SLA_HOURS.get(i["priority"], 8)
    try:
        elapsed = (dt.datetime.now() - dt.datetime.fromisoformat(i["created_at"])).total_seconds() / 3600
    except Exception:
        elapsed = 0.0
    rem = target - elapsed
    return "BREACHED" if rem <= 0 else f"{int(rem)}h {int((rem % 1) * 60)}m left"


# ================================================================= Collapsible sections (Incidents page)
def _render_incident_detail(dom, ref, you_role):
    """The selected incident's details — rendered in the incident dialog."""
    lens = st.radio("View", ["Resolution thread", "Act & verify (guided)"], horizontal=True,
                    key="ws_mode_" + ref, label_visibility="collapsed",
                    help="The thread explains what happened; the guided view is where you execute, "
                         "verify and close.")
    if dom == "DataOps":
        data = DE.load()
        inc = next((i for i in data["incidents"] if i["id"] == ref), None)
        if inc is None:
            st.warning("Incident not found.")
            return
        if lens == "Resolution thread":
            command_center.dop_command(inc, data)
        else:
            DV.pipeline_view(inc, data)
    else:
        ctx = _it_ctx()
        inc = _find_it(ref)
        if inc is None:
            st.warning("Incident not found.")
            return
        if lens == "Resolution thread":
            command_center.it_command(inc, ctx)
        else:
            personas.incident_view(inc, ctx)


def _open(dom, ref):
    """Open an incident workspace (page-level, so the browser keeps a real URL and Back works)."""
    st.session_state["nav"] = journey.WORKSPACE_NAV
    st.session_state["open_incident"] = {"domain": dom, "ref": ref}


def _close_workspace():
    """Leave the workspace for the list — and drop the deep link, or it would reopen on the rerun."""
    st.session_state.pop("open_incident", None)
    st.session_state["_deep_done"] = True
    try:
        if "inc" in st.query_params:
            del st.query_params["inc"]
    except Exception:
        pass


def _all_refs():
    """Board order: open first, then priority, then id — used for prev/next in the workspace."""
    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    rows = [("IT Ops", i) for i in _it_inc] + [("DataOps", i) for i in _dop_inc]
    rows.sort(key=lambda r: (r[1].get("status") != "open", order.get(r[1].get("priority"), 9), r[1]["id"]))
    return rows


def _participants(inc):
    """People already engaged on the thread, with the owning team first."""
    names = list(journey.collab_stats(inc)["participants"])
    owner = inc.get("owner_team")
    if owner and owner not in names:
        names.insert(0, owner)
    return names[:6]


def _ask_targets(dom, inc=None):
    teams = {s.get("owner") for s in _sv.values() if s.get("owner")}
    teams |= {d.get("owner_team") for d in _dop_data["datasets"].values() if d.get("owner_team")}
    teams |= {i.get("owner_team") for i in list(_it_inc) + list(_dop_inc) if i.get("owner_team")}
    roles = ["Data Owner", "Incident Manager", "CSM", "Data Engineer", "Platform Engineer", "Developer"]
    options = sorted(teams) + [r for r in roles if r not in teams]
    owner = (inc or {}).get("owner_team")
    if owner in options:                      # the incumbent owner is the most likely person to ask
        options.remove(owner)
        options.insert(0, owner)
    return options


def _collab_bar(dom, ref, you_role):
    """One obvious place to collaborate: who is on it, what we are waiting for, and a way to ask
    someone for something specific with a deadline — logged on the thread instead of floating in chat."""
    inc = _find_dop(ref) if dom == "DataOps" else _find_it(ref)
    if inc is None:
        return
    asks = [d for d in collab.delegations(ref) if d["status"] != "done"]
    waiting = None
    if asks:
        oldest = min(asks, key=lambda d: d["ts"] or "")
        try:
            mins = int((dt.datetime.now() - dt.datetime.fromisoformat(oldest["ts"])).total_seconds() / 60)
        except Exception:
            mins = 0
        age = f"{mins} min" if mins < 90 else f"{mins // 60}h {mins % 60:02d}m"
        waiting = f'Waiting {age} · {oldest["to_"]}'
    c1, c2, c3 = st.columns([6.4, 1.25, 0.95], vertical_alignment="center")
    with c1:
        viz.collab_chips(_participants(inc), waiting)
    with c2:
        with st.popover("Collaborate", type="primary", width="stretch"):
            st.markdown("**Bring someone in**")
            st.caption("Creates a request on this thread with a deadline — not another side chat.")
            # A form, not loose widgets: typing does not rerun the page, so the popover stays open and
            # the presenter can type and then press Send without losing what they wrote.
            with st.form(key=f"ask_form_{ref}", clear_on_submit=True, border=False):
                who = st.selectbox("Who", _ask_targets(dom, inc), key=f"ask_who_{ref}")
                what = st.text_input("What do you need", key=f"ask_what_{ref}",
                                     placeholder="e.g. confirm contract v4 is deployed")
                mins = st.select_slider("Expected back in", [15, 30, 60, 120], value=30,
                                        format_func=lambda m: f"{m} min", key=f"ask_when_{ref}")
                channel = st.radio("Channel", ["Teams", "Slack", "Email", "App"], horizontal=True,
                                   key=f"ask_ch_{ref}")
                sent = st.form_submit_button("Send request", type="primary", width="stretch")
            if sent:
                if not what.strip():
                    st.warning("Say what you need before sending.")
                else:
                    act = f'{what.strip()} · expected in {mins} min'
                    collab.add_delegation(ref, you_role, who, act, channel=channel,
                                          stage=journey.lifecycle_stage(inc))
                    collab.add_comment(ref, you_role, "Person", f'Asked **{who}**: {act}',
                                       channel=channel, stage=journey.lifecycle_stage(inc))
                    collab.add_notification(collab.ACTOR_TO_ROLE.get(who, "Incident Manager"), ref,
                                            f'{you_role} asked you: {what.strip()}')
                    st.session_state["flash"] = (f"Request sent to {who} — it is on the thread with a "
                                                 f"{mins} min clock.")
                    st.rerun()
    with c3:
        with st.popover("Share", width="stretch"):
            st.caption("Stable link to this thread.")
            st.code(f'?inc={ref}', language=None)

    def _age_min(d):
        try:
            return int((dt.datetime.now() - dt.datetime.fromisoformat(d["ts"])).total_seconds() / 60)
        except Exception:
            return 0

    if asks:
        with st.expander(f"Open requests · {len(asks)}"
                         + (" · overdue" if any(_age_min(d) > 30 for d in asks) else ""),
                         expanded=False):
            for d in sorted(asks, key=lambda d: d["ts"] or "", reverse=True):
                age = _age_min(d)
                late = age > 30                      # default response expectation until per-request SLAs land
                state = {"assigned": "sent", "accepted": "acknowledged"}.get(d["status"], d["status"])
                tone = "#b91c1c" if late else ("#166534" if d["status"] == "accepted" else "#92400e")
                cols = st.columns([5.6, 1, 1], vertical_alignment="center")
                cols[0].markdown(
                    f'**{d["to_"]}** · {d["action"]}  \n'
                    f'<span style="color:{tone};font-size:11.5px;font-weight:650">'
                    f'{"OVERDUE · " if late else ""}{state}</span>'
                    f'<span style="color:#64748b;font-size:11.5px"> · asked by {d["frm"]} · {age} min ago · '
                    f'{d.get("channel") or "App"}</span>', unsafe_allow_html=True)
                if cols[1].button("Done", key=f"ask_done_{d['id']}", width="stretch"):
                    collab.set_delegation_status(d["id"], "done")
                    collab.add_comment(ref, d["to_"], "Person", f'Done: {d["action"]}')
                    st.session_state["flash"] = f'Marked done — {d["to_"]} replied on the thread.'
                    st.rerun()
                if cols[2].button("Chase", key=f"ask_chase_{d['id']}", width="stretch"):
                    collab.add_comment(ref, you_role, "Person", f'Chased {d["to_"]} for: {d["action"]}')
                    st.session_state["flash"] = f'Reminder logged to {d["to_"]}.'
                    st.rerun()
            done = [d for d in collab.delegations(ref) if d["status"] == "done"][:4]
            if done:
                st.caption("Completed")
                for d in done:
                    c = st.columns([6, 1], vertical_alignment="center")
                    c[0].markdown(f'~~{d["to_"]} · {d["action"]}~~', unsafe_allow_html=True)
                    if c[1].button("Reopen", key=f"ask_reopen_{d['id']}", width="stretch"):
                        collab.set_delegation_status(d["id"], "assigned")
                        st.session_state["flash"] = f'Reopened the request to {d["to_"]}.'
                        st.rerun()
    else:
        st.caption("No open requests on this incident — use **Collaborate** to ask someone, with a deadline.")


_WS_PANEL_HEIGHT = 470      # px; the workspace body scrolls inside this, the header stays put

_STAGE_ACTION = {
    "Detect": ("Confirm signal", "Correlate", "Check the affected service and the first evidence."),
    "Correlate": ("Confirm cause", "Correlate", "Weigh observed evidence against inferred links."),
    "Coordinate": ("Bring in owner", "Coordinate", "Request an owner or approval with a deadline."),
    "Act": ("Execute fix", "Act", "Risk-gated: approval is required before execution."),
    "Verify": ("Verify now", "Verify", "The verdict here decides whether closure is possible."),
    "Close": ("Close incident", "Close", "Closure is gated on the authoritative verification."),
}


def _go_stage(dom, ref, stage):
    """Primary action callback — switch the workspace to the guided view at the stage that matters."""
    prefix = "dop" if dom == "DataOps" else "it"
    st.session_state[f"ws_mode_{ref}"] = "Act & verify (guided)"
    st.session_state[f"{prefix}_step_{ref}"] = stage


def _close_now(ref, you_role):
    ok, msg = journey.close_incident(ref, you_role)
    st.session_state["flash"] = msg


def render_workspace_page(dom, ref, you_role):
    """Full-page incident workspace: a sticky identity bar with the one action that matters now,
    then the collaboration bar, then the thread or the guided execution view."""
    inc = _find_dop(ref) if dom == "DataOps" else _find_it(ref)
    if inc is None:
        viz.page_head("Incident not found", f"No incident with id {ref}.")
        st.button("← All incidents", on_click=_close_workspace)
        return

    stage = journey.lifecycle_stage(inc)
    verdict = journey.current_verdict(inc)
    gate = journey.closure_state(inc)
    closed = gate["closed"]
    sev = viz.SEV_LABEL.get(inc.get("priority"), ("", "Minor"))[1]
    sla = _sla_txt(inc) if not closed else "closed"
    tone = {"Verified": "#16a34a", "Mitigated": "#d97706", "Recovery failed": "#dc2626",
            "Inconclusive": "#7c3aed"}.get(verdict, "#475569")
    nxt = journey.next_action(inc, stage)
    action_label, action_stage, action_why = nxt["label"], nxt["stage"], nxt["why"]
    if not action_label:
        action_stage = "Close"
    shell.incident_context(inc["id"], verdict, tone, sev, nxt["stage"], sla)

    viz.crumb("All incidents", _close_workspace)
    with st.container(key=f"ws_head_{ref}"):
        c1, c2 = st.columns([6.4, 1.5], vertical_alignment="center")
        with c1:
            st.markdown(
                f'<div class="ri-wsid"><span class="id">{inc["id"]}</span>'
                f'<span class="chip" style="background:{tone}1a;color:{tone}">{verdict}</span>'
                f'<span class="meta">{sev} · <b>{nxt["stage"]}</b> · <b>{sla}</b></span></div>',
                unsafe_allow_html=True)
        if action_label:
            if action_stage == "Close" and gate["eligible"]:
                c2.button(action_label, type="primary", width="stretch", key="ws_primary",
                          on_click=_close_now, args=(ref, you_role))
            elif action_stage == "Close":
                c2.button("See blockers", width="stretch", key="ws_primary",
                          on_click=lambda: st.session_state.update({"ws_show_gate": True}))
            elif action_stage == "Coordinate":
                c2.button(action_label, type="primary", width="stretch", key="ws_primary",
                          on_click=_go_stage, args=(dom, ref, "Coordinate"), help=action_why)
            else:
                c2.button(action_label, type="primary", width="stretch", key="ws_primary",
                          on_click=_go_stage, args=(dom, ref, action_stage), help=action_why)
    refs = _all_refs()
    idx = next((n for n, (_d, i) in enumerate(refs) if i["id"] == ref), None)
    if idx is not None:
        p1, p2, p3 = st.columns([6.2, 0.9, 0.9], vertical_alignment="center")
        p1.caption(f'{idx + 1} of {len(refs)} in the queue · {action_why}')
        if idx > 0 and p2.button("← Previous", key="ws_prev", width="stretch"):
            prev_dom, prev_inc = refs[idx - 1]
            _open(prev_dom, prev_inc["id"])
            st.rerun()
        if idx < len(refs) - 1 and p3.button("Next →", key="ws_next", width="stretch"):
            nxt_dom, nxt_inc = refs[idx + 1]
            _open(nxt_dom, nxt_inc["id"])
            st.rerun()

    _collab_bar(dom, ref, you_role)
    st.query_params["inc"] = ref
    # The thread scrolls inside its own panel, so the identity bar above never leaves the screen —
    # this is the only construction that pins on Streamlit Cloud, where the app lives in an
    # auto-height iframe and the outer page (not the app) is what scrolls.
    with st.container(height=_WS_PANEL_HEIGHT, border=True):
        _render_incident_detail(dom, ref, you_role)
        # The guided view puts the gate inside its own Close step; rendering it twice reads as a bug.
        if st.session_state.get(f"ws_mode_{ref}") != "Act & verify (guided)":
            st.divider()
            _asks = [d for d in collab.delegations(ref) if d["status"] != "done"]

            def _finish(d):
                collab.set_delegation_status(d["id"], "done")
                st.session_state["flash"] = f'Marked done — {d["to_"]} replied on the thread.'

            viz.closure_gate(journey.closure_state(inc),
                             on_close=lambda: journey.close_incident(ref, you_role),
                             actor=you_role, expanded=st.session_state.pop("ws_show_gate", False),
                             asks=_asks, on_done=_finish, prefix=f"page_{ref}")


def _incident_rows():
    rows = [{"domain": "IT Ops", "inc": i, "verdict": journey.display_verdict(i)} for i in _it_inc]
    rows += [{"domain": "DataOps", "inc": i, "verdict": journey.display_verdict(i)} for i in _dop_inc]
    return rows


def render_incidents(you_role):
    """Incident page: one header, one filter bar, one list. No nested expanders hiding the work."""
    if "inc" in st.query_params:
        del st.query_params["inc"]
    rows = _incident_rows()
    n_open = sum(1 for r in rows if r["inc"].get("status") == "open")
    n_risk = sum(1 for r in rows if r["inc"].get("status") == "open" and _sla_risk(r["inc"]))
    n_cross = sum(1 for r in rows if journey.correlation_for(r["inc"]["id"]))
    viz.page_head("Incidents",
                  f"<b>{n_open}</b> open · <b>{n_risk}</b> at SLA risk · <b>{n_cross}</b> cross-domain "
                  f"· {len(rows)} total")

    # Filters must survive a trip into an incident and back: Streamlit drops a widget's state when the
    # widget is not rendered, so the values are mirrored in plain session keys and restored here.
    _defaults = {"board_q": "", "board_dom": "All", "board_status": "All",
                 "board_verdict": "All", "board_pri": "All"}
    for _k, _v in _defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = st.session_state.get(f"keep_{_k}", _v)

    f1, f2, f3, f4, f5, f6 = st.columns([2.4, 1.1, 1.0, 1.3, 0.9, 1.0], vertical_alignment="bottom")
    q = f1.text_input("Search", placeholder="id · title · owner", key="board_q")
    domf = f2.selectbox("Domain", ["All", "IT Ops", "DataOps"], key="board_dom")
    statf = f3.selectbox("Status", ["All", "Open", "Closed"], key="board_status")
    verf = f4.selectbox("Verdict", ["All"] + VERDICT_OPTIONS, key="board_verdict")
    prif = f5.selectbox("Priority", ["All", "P1", "P2", "P3"], key="board_pri")
    risk_only = f6.checkbox("SLA at risk", key="board_risk")
    for _k in _defaults:
        st.session_state[f"keep_{_k}"] = st.session_state.get(_k, _defaults[_k])
    st.session_state["keep_board_risk"] = bool(risk_only)

    def _reset_filters():
        for k, v in (("board_q", ""), ("board_dom", "All"), ("board_status", "All"),
                     ("board_verdict", "All"), ("board_pri", "All"), ("board_risk", False)):
            st.session_state[k] = v
            st.session_state[f"keep_{k}"] = v
        st.session_state.pop("scope_note", None)
        st.session_state["_gs_drives_board"] = False

    def _match(r):
        inc = r["inc"]
        blob = (inc["id"] + " " + inc["title"] + " " + (inc.get("owner_team") or "")).lower()
        return (not q or q.lower() in blob) \
            and (domf == "All" or r["domain"] == domf) \
            and (statf == "All" or (inc.get("status") or "").lower() == statf.lower()) \
            and (verf == "All" or r["verdict"] == verf) \
            and (prif == "All" or inc.get("priority") == prif) \
            and (not risk_only or _sla_risk(inc))

    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    shown = sorted((r for r in rows if _match(r)),
                   key=lambda r: (r["inc"].get("status") != "open",
                                  order.get(r["inc"].get("priority"), 9), r["inc"]["id"]))

    scope = st.session_state.get("scope_note")
    active = []
    if scope:
        active.append(scope)
    if q and not (scope and q.lower() in scope.lower()):
        active.append(f"search: {q}")
    if domf != "All":
        active.append(domf)
    if statf != "All":
        active.append(statf)
    if verf != "All":
        active.append(verf)
    if prif != "All":
        active.append(prif)
    if risk_only:
        active.append("SLA at risk")
    c1, c2 = st.columns([5.4, 1.2], vertical_alignment="center")
    with c1:
        if active:
            chips = []
            if scope:
                chips.append(f'<span class="ri-scope">{scope}</span>')
            for a in active:
                if scope and a == scope:
                    continue
                chips.append(f'<span class="ri-filterchip">{a}</span>')
            st.markdown(" ".join(chips), unsafe_allow_html=True)
        else:
            st.caption(f"Showing {len(shown)} incidents · open first, then priority")
    with c2:
        if active:
            st.button("Reset filters", key="board_reset", on_click=_reset_filters, width="stretch")

    if not shown:
        what = " · ".join(active) if active else "no filters"
        st.info(f"No incidents match **{what}**. The filter is applied to open and closed incidents "
                f"in both domains.")
        c1, c2 = st.columns([1, 5])
        c1.button("Clear filters", key="board_clear", on_click=_reset_filters)
        c2.caption("Open an incident from the list, or clear the scope to see everything again.")
        return

    view = st.segmented_control("View", ["List", "Board"], default="List", key="board_view",
                                label_visibility="collapsed") or "List"

    if view == "List":
        asks = {}
        for r in shown:
            open_asks = [d for d in collab.delegations(r["inc"]["id"]) if d["status"] != "done"]
            if open_asks:
                oldest = min(open_asks, key=lambda d: d["ts"] or "")
                try:
                    mins = int((dt.datetime.now() - dt.datetime.fromisoformat(oldest["ts"])).total_seconds() / 60)
                except Exception:
                    mins = 0
                age = f"{mins}m" if mins < 90 else f"{mins // 60}h {mins % 60:02d}m"
                asks[r["inc"]["id"]] = f'{oldest["to_"]} · {age}'
        for r in shown:
            viz.list_row(r["inc"], r["domain"], r["verdict"], on_click=_open,
                         args=(r["domain"], r["inc"]["id"]), stage=journey.lifecycle_stage(r["inc"]),
                         sla=(_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else "closed"),
                         waiting=asks.get(r["inc"]["id"]),
                         linked=bool(journey.correlation_for(r["inc"]["id"])))
    else:
        cross = [r for r in shown if journey.correlation_for(r["inc"]["id"])]
        single = [r for r in shown if not journey.correlation_for(r["inc"]["id"])]

        def _cards(subset):
            cols = st.columns(2)
            for i, r in enumerate(subset):
                with cols[i % 2]:
                    viz.board_card(r["inc"], r["domain"], r["verdict"],
                                   on_click=_open, args=(r["domain"], r["inc"]["id"]),
                                   stage=journey.lifecycle_stage(r["inc"]),
                                   sla=(_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else None),
                                   linked=bool(journey.correlation_for(r["inc"]["id"])))
        if cross:
            viz.section("Cross-domain threads", "resolved together as one governed thread")
            _cards(cross)
        if single:
            viz.section("Single-domain", "independent IT Ops or DataOps incidents")
            _cards(single)

    with st.expander("Live events · simulated", expanded=False):
        viz.feed(realtime.recent(8))


# ================================================================= Analytics
def render_analytics():
    st.subheader("Analytics — resolution performance")
    st.caption("Every figure states its provenance: **live** numbers are computed from the sample "
               "incidents on this system; **illustrative** numbers are scenario estimates. Nothing here "
               "is presented as a measured result unless it is.")

    incidents = list(_it_inc) + list(_dop_inc)
    verdicts = [journey.display_verdict(i) for i in incidents]
    closed = [i for i in incidents if (i.get("status") or "").lower() != "open"]
    n_open = len(incidents) - len(closed)
    n_verified = sum(1 for i in closed if journey.display_verdict(i) == "Verified")
    at_risk = sum(1 for i in incidents if i.get("status") == "open" and _sla_risk(i))
    cross = sum(1 for i in incidents if journey.thread_edges_for(i["id"]))
    vcr = f'{n_verified}/{len(closed)}' if closed else "—"

    viz.kpi_row([
        ("Incidents", len(incidents), f'{n_open} open · {len(closed)} closed', "#4f46e5"),
        ("Verified closure", vcr, "closed only after independent verification", "#16a34a"),
        ("Cross-domain threads", cross, f'of {len(incidents)} incidents', "#7c3aed"),
        ("SLA at risk", at_risk, "open incidents inside 50% of target", "#dc2626"),
    ])
    viz.data_badge("live")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Resolution outcomes")
        oc = ["Investigating", "Mitigated", "Verified", "Recovery failed"]
        df = pd.DataFrame({"Outcome": oc, "Incidents": [verdicts.count(v) for v in oc]})
        st.altair_chart(viz.chart_bars(df, "Outcome", "Incidents", height=230), width="stretch")
        st.caption("Live — authoritative verdict counts. Zero-value outcomes stay on the axis.")
    with right:
        st.markdown("#### Incidents by domain")
        dom = pd.DataFrame([
            {"Domain": "IT Ops", "State": "Open", "n": sum(1 for i in _it_inc if i.get("status") == "open")},
            {"Domain": "IT Ops", "State": "Closed", "n": sum(1 for i in _it_inc if i.get("status") != "open")},
            {"Domain": "DataOps", "State": "Open", "n": sum(1 for i in _dop_inc if i.get("status") == "open")},
            {"Domain": "DataOps", "State": "Closed", "n": sum(1 for i in _dop_inc if i.get("status") != "open")},
        ])
        dom["State"] = pd.Categorical(dom["State"], categories=["Closed", "Open"], ordered=True)
        dom = dom.sort_values("State")
        st.altair_chart(viz.chart_bars(dom, "Domain", "n", group="State", height=230), width="stretch")
        st.caption("Live — incident distribution across the two operational domains.")

    st.markdown("#### MTTR — baseline vs with the platform")
    mttr = pd.DataFrame([
        {"Month": m, "Series": "Baseline (h)", "Hours": b}
        for m, b in zip(["Jan", "Feb", "Mar", "Apr", "May", "Jun"], [7.8, 7.6, 8.1, 7.9, 8.0, 7.7])
    ] + [
        {"Month": m, "Series": "With platform (h)", "Hours": b}
        for m, b in zip(["Jan", "Feb", "Mar", "Apr", "May", "Jun"], [7.6, 6.9, 5.8, 4.6, 3.2, 2.4])
    ])
    mttr["Series"] = pd.Categorical(mttr["Series"], categories=["Baseline (h)", "With platform (h)"], ordered=True)
    mttr = mttr.sort_values("Series")
    st.altair_chart(viz.chart_lines(mttr, "Month", "Hours", "Series", height=250), width="stretch")
    viz.data_badge("illus")
    st.caption("MTTR falling as cross-domain correlation and coordination kick in — a scenario estimate, "
               "to be measured against a real baseline in a pilot.")

    st.markdown("#### Where the time goes — baseline vs with the platform")
    steps = pd.DataFrame([
        {"Step": "Identify likely cause", "Series": "Baseline", "Minutes": 45},
        {"Step": "Assign next owner", "Series": "Baseline", "Minutes": 30},
        {"Step": "Verified recovery", "Series": "Baseline", "Minutes": 240},
        {"Step": "Identify likely cause", "Series": "With platform", "Minutes": 10},
        {"Step": "Assign next owner", "Series": "With platform", "Minutes": 2},
        {"Step": "Verified recovery", "Series": "With platform", "Minutes": 60},
    ])
    steps["Series"] = pd.Categorical(steps["Series"], categories=["Baseline", "With platform"], ordered=True)
    steps = steps.sort_values("Series")
    st.altair_chart(viz.chart_bars(steps, "Step", "Minutes", group="Series", height=250), width="stretch")
    viz.data_badge("illus")
    st.caption("Minutes per step: the acceleration the platform targets. Scenario values, not measurements.")

    st.markdown("#### SLA / OLA breaches per month")
    br = pd.DataFrame({"Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
                       "Breaches": [6, 6, 5, 4, 3, 2]})
    st.altair_chart(viz.chart_bars(br, "Month", "Breaches", height=230, muted=True), width="stretch")
    viz.data_badge("illus")
    st.caption("Monthly breach totals — illustrative, in chronological order.")


# ================================================================= Activity & audit (page)
def render_activity():
    st.subheader("Activity & audit — actions, handoffs, verification")
    st.caption("Persisted records from the current data (sample).")
    refs = [i["id"] for i in _it_inc] + [i["id"] for i in _dop_inc]
    t1, t2, t3 = st.tabs(["Comments", "Handoffs", "Verification records"])
    with t1:
        rows = []
        for r in refs:
            for cm in collab.comments(r):
                rows.append({"ref": r, "ts": cm["ts"], "author": cm["author"],
                             "channel": cm.get("channel") or "—", "stage": cm.get("stage") or "—",
                             "text": cm["text"]})
        rows.sort(key=lambda x: x["ts"], reverse=True)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(640, max(160, 38 * len(rows) + 40)))
        else:
            st.caption("No comments.")
    with t2:
        rows = []
        for r in refs:
            for d in collab.delegations(r):
                rows.append({"ref": r, "from": d["frm"], "to": d["to_"], "action": d["action"],
                             "status": d["status"], "channel": d.get("channel") or "—",
                             "stage": d.get("stage") or "—", "ts": d["ts"]})
        rows.sort(key=lambda x: x["ts"], reverse=True)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(640, max(160, 38 * len(rows) + 40)))
        else:
            st.caption("No handoffs.")
    with t3:
        rows = []
        for r in refs:
            rec = journey.resolution_record(r)
            if rec:
                rows.append({"ref": r, "verdict": rec.get("verdict"), "action": rec.get("action_id"),
                             "actor": rec.get("actor"), "closed_at": rec.get("closed_at") or "—",
                             "checks": len(rec.get("checks") or [])})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(640, max(160, 38 * len(rows) + 40)))
        else:
            st.caption("No verification records yet — apply a remediation to create one.")


# ================================================================= dispatch
if nav == journey.WORKSPACE_NAV:
    _sel = st.session_state.get("open_incident")
    if _sel:
        render_workspace_page(_sel["domain"], _sel["ref"], you_role)
    else:
        render_incidents(you_role)
elif nav == "Analytics":
    render_analytics()
elif nav == "Activity & audit":
    render_activity()

if not st.session_state.get("open_incident"):
    st.divider()
    st.caption(f"Sample data · simulated actions · {build.label()} — proof of concept, not production. "
               "See PROTOTYPE_NOTES.md for persistence limits and TESTS.md for the test suite.")
