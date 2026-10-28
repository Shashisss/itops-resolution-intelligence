#!/usr/bin/env python3
"""Resolution Intelligence — Streamlit POC.
One governed platform across IT Ops and DataOps.
Unified shell · one incident workspace · one lifecycle · one status vocabulary.
Deterministic graph + rule-based reasoning. SAMPLE DATA · SIMULATED ACTIONS."""
import os
import datetime as dt
import importlib
import pathlib
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import engine as E
import personas
import dataops_engine as DE
import dataops_views as DV
import command_center
import viz
import journey
import collab
import analytics
import learn
import shell
import workspace
import realtime


_RELOAD_TARGETS = (viz, journey, collab, analytics, learn, E, DE, personas, DV, workspace,
                   command_center, shell, realtime)


def _refresh_modules():
    """Reload our own modules so the running app always matches app.py.

    Streamlit Cloud can hot-reload app.py while leaving imported sibling modules cached at an
    older build — which caused AttributeError (missing helpers) and TypeError (missing params,
    e.g. board_card(linked=…)) on newly added code. importlib.reload mutates the module object in
    place, so every importer sees the refreshed definitions. Doing this every run is cheap (the
    modules only define functions) and removes the whole class of stale-module failures.

    A failed reload is returned rather than swallowed: silently keeping the old definition is how
    a deploy looks healthy while running last release's code. The caller surfaces it in the UI."""
    failures = []
    for _m in _RELOAD_TARGETS:
        try:
            importlib.reload(_m)
        except Exception as exc:  # noqa: BLE001 — one bad module must not take the app down
            failures.append({"module": getattr(_m, "__name__", str(_m)),
                             "error": f"{type(exc).__name__}: {exc}"})
    return failures


_RELOAD_FAILURES = _refresh_modules()

VERDICT_OPTIONS = ["Investigating", "Mitigated", "Verified", "Recovery failed", "Inconclusive"]


def _current_version():
    """The version this checkout is running, from the same file build.label() uses."""
    try:
        return pathlib.Path(__file__).with_name("VERSION").read_text().strip()
    except Exception:
        return ""


def _needs_seed():
    """Seed when the database is missing/incomplete or was built by another release.

    Comparing against VERSION (not a hardcoded string) means a schema change shipped with a bump
    forces a reseed instead of leaving an old file that is missing a column."""
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
        version = _current_version()
        return not (v and version and v[0] == version)
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
for _mod in (E, DE, journey, collab, analytics, realtime):
    _mod.DB = _DB_PATH
learn.DB = _DB_PATH          # learn records live outside the session copy on purpose (durable)
_DEMO_SESSION = store.is_demo()

st.set_page_config(page_title="Resolution Intelligence — POC", page_icon="assets/icon.png",
                   layout="wide")
viz.inject_css()
viz.platform_offset()

if _RELOAD_FAILURES:
    _bad = ", ".join(f'{f["module"]} ({f["error"]})' for f in _RELOAD_FAILURES)
    st.error(
        f"**Hot reload incomplete** — {len(_RELOAD_FAILURES)} module(s) failed to reload: {_bad}. "
        "This page may be running stale code; restart the app before trusting the view.")
    with st.expander("Reload failure detail"):
        for f in _RELOAD_FAILURES:
            st.code(f'{f["module"]}: {f["error"]}', language=None)
        st.caption(f'Build {build.label(short=True)} · if the error names a syntax/missing symbol, '
                   "fix the module and redeploy — a reload cannot repair broken source.")

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
        _deep_step = str(st.query_params.get("step") or "").strip().title()
        if _deep_step in journey.LIFECYCLE:
            _prefix = "dop" if _deep_dom == "DataOps" else "it"
            st.session_state[f"ws_mode_{_deep_ref}"] = "Act & verify (guided)"
            st.session_state[f"{_prefix}_step_{_deep_ref}"] = _deep_step
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
    _prev_lens = st.session_state.get("_lens_" + ref)
    if _prev_lens is not None and _prev_lens != lens:
        # A stage action sets a more specific target first; switching the lens must not overwrite it.
        st.session_state.setdefault("_scroll_anchor", f"ws_lens_{ref}")
    st.session_state["_lens_" + ref] = lens
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
            st.caption("Logs a request on this thread with a deadline. **Simulated: nothing is sent.** "
                       "No Teams, Slack or email connector is configured, so the channel below is "
                       "recorded as the intended route only.")
            # A form, not loose widgets: typing does not rerun the page, so the popover stays open and
            # the presenter can type and then press Send without losing what they wrote.
            with st.form(key=f"ask_form_{ref}", clear_on_submit=True, border=False):
                who = st.selectbox("Who", _ask_targets(dom, inc), key=f"ask_who_{ref}")
                what = st.text_input("What do you need", key=f"ask_what_{ref}",
                                     placeholder="e.g. confirm contract v4 is deployed")
                mins = st.select_slider("Expected back in", [15, 30, 60, 120], value=30,
                                        format_func=lambda m: f"{m} min", key=f"ask_when_{ref}")
                channel = st.radio("Intended channel (recorded only)", ["Teams", "Slack", "Email", "App"],
                                   horizontal=True, key=f"ask_ch_{ref}")
                sent = st.form_submit_button("Log request — not sent", type="primary", width="stretch")
            if sent:
                if not what.strip():
                    st.warning("Say what you need before logging the request.")
                else:
                    act = f'{what.strip()} · expected in {mins} min'
                    collab.add_delegation(ref, you_role, who, act, channel=channel,
                                          stage=journey.lifecycle_stage(inc))
                    collab.add_comment(ref, you_role, "Person",
                                       f'Asked **{who}**: {act} (simulated — not delivered)',
                                       channel=channel, stage=journey.lifecycle_stage(inc))
                    collab.add_notification(collab.ACTOR_TO_ROLE.get(who, "Incident Manager"), ref,
                                            f'[Simulated · not delivered] {you_role} asked you: {what.strip()}')
                    st.session_state["flash"] = (
                        f"Request logged on the thread for {who} with a {mins} min clock. "
                        f"Simulated — it was NOT delivered: no {channel} connector is configured.")
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
                late = collab.is_overdue(d, 30)      # default response expectation until per-request SLAs land
                state = {"assigned": "sent · not delivered", "accepted": "acknowledged",
                         "reopened": "reopened"}.get(d["status"], d["status"])
                tone = "#b91c1c" if late or d["status"] == "reopened" else (
                    "#166534" if d["status"] == "accepted" else "#92400e")
                actor = d.get("actor") or "unknown"
                when = str(d.get("changed_at") or d.get("ts") or "")
                when_show = when[11:16] if len(when) >= 16 else when
                cols = st.columns([5.1, 0.8, 0.8, 0.8], vertical_alignment="center")
                cols[0].markdown(
                    f'**{d["to_"]}** · {d["action"]}  \n'
                    f'<span style="color:{tone};font-size:11.5px;font-weight:650">'
                    f'{"OVERDUE · " if late else ""}{state}</span>'
                    f'<span style="color:#64748b;font-size:11.5px"> · by {actor} · {when_show} · '
                    f'asked {age} min ago · {d.get("channel") or "App"} (recorded, simulated)</span>',
                    unsafe_allow_html=True)
                if cols[1].button("Ack", key=f"ask_ack_{d['id']}", width="stretch",
                                  disabled=d["status"] == "accepted"):
                    collab.set_delegation_status(d["id"], "accepted", actor=d["to_"])
                    collab.add_comment(ref, d["to_"], "Person",
                                       f'Acknowledged: {d["action"]} (simulated)')
                    st.session_state["flash"] = f'Acknowledged by {d["to_"]} on the thread (simulated).'
                    st.rerun()
                if cols[2].button("Done", key=f"ask_done_{d['id']}", width="stretch"):
                    collab.set_delegation_status(d["id"], "done", actor=d["to_"])
                    collab.add_comment(ref, d["to_"], "Person", f'Done: {d["action"]} (simulated)')
                    st.session_state["flash"] = f'Marked done — {d["to_"]} replied on the thread (simulated).'
                    st.rerun()
                if cols[3].button("Chase", key=f"ask_chase_{d['id']}", width="stretch"):
                    collab.add_comment(ref, you_role, "Person",
                                       f'Chased {d["to_"]} for: {d["action"]} (simulated)')
                    st.session_state["flash"] = f'Reminder logged to {d["to_"]} (simulated).'
                    st.rerun()
            done = [d for d in collab.delegations(ref) if d["status"] == "done"][:4]
            if done:
                st.caption("Completed")
                for d in done:
                    c = st.columns([6, 1], vertical_alignment="center")
                    c[0].markdown(f'~~{d["to_"]} · {d["action"]}~~', unsafe_allow_html=True)
                    if c[1].button("Reopen", key=f"ask_reopen_{d['id']}", width="stretch"):
                        collab.set_delegation_status(d["id"], "reopened", actor=you_role)
                        collab.add_comment(ref, you_role, "Person",
                                           f'Reopened the request to {d["to_"]}: {d["action"]} (simulated)')
                        st.session_state["flash"] = f'Reopened the request to {d["to_"]} (simulated).'
                        st.rerun()
    else:
        st.caption("No open requests on this incident — use **Collaborate** to ask someone, with a deadline.")


def _ws_panel_css(ref):
    """The page scrolls; the identity bar stays pinned to the top of it.

    Two earlier shapes were wrong. v93 gave the thread a clamp(300–560px) box, which turned the
    guided walkthrough into a keyhole. v96 removed the keyhole but kept the content in a section of
    its own that scrolled — the page did not move, one box did, and that still reads as "the page is
    stuck".

    Now there is one scroll surface and it is the page: the thread and the walkthrough flow at full
    length in [data-testid="stMain"], and the identity bar is pinned by *its own layout wrapper*
    (see the sticky rule in viz.CSS) rather than by the bar itself. That detail is what makes it
    work: Streamlit wraps every container in a layout div of exactly the bar's height, so sticky on
    the bar has no room to travel, and the older display:contents workaround for that left the bar
    painted under the content it was supposed to cover. The wrapper is a child of the tall content
    column, so it has room, and nothing is taken out of flow.
    """
    key = f"ws_panel_{ref}"
    st.markdown(
        f"""<style>
        [data-testid="stMain"] {{ overflow-y: auto !important; }}
        .st-key-{key} {{
            flex: 0 0 auto !important;
            height: auto !important;
            max-height: none !important;
            overflow: visible !important;
        }}
        [class*="_anchor_"], .st-key-ws_gate_ {{ scroll-margin-top: var(--ri-offset, 66px); }}
        </style>""", unsafe_allow_html=True)


def _scroll_to_anchor(key, settle_ms=4000):
    """Jump to a rendered section after an action.

    Streamlit cannot move the viewport from the server, so this is a few lines of DOM code sent with
    the page. It goes through components.html rather than st.html because a component iframe
    re-executes its script on every rerun (st.html runs only when the node is first created, so the
    second click jumped nowhere).

    It assigns the scroll container's scrollTop instead of calling scrollIntoView — a smooth
    animation is interrupted by Streamlit's re-render and stops halfway. The correction loop runs for
    a few seconds on requestAnimationFrame because the sections above the target (expanders, charts)
    settle after the jump and move it again. --ri-offset (the pinned bar plus a little air, measured
    by viz.platform_offset) is where the target lands, so the bar never covers the section. A missing
    element is a silent no-op: a demo never shows a scroll error."""
    components.html(
        "<script>(function(){try{var d=window.parent.document;var t0=Date.now();"
        "function box(){return d.querySelector('[data-testid=\"stMain\"]')||d.scrollingElement;}"
        "function go(){var el=d.querySelector('[class*=\"st-key-" + key + "\"]');if(!el)return;"
        "var c=box();if(!c)return;"
        "var cs=d.defaultView.getComputedStyle(d.documentElement);"
        "var bars=parseFloat(cs.getPropertyValue('--ri-offset'))||66;"
        "var top=(c.getBoundingClientRect?c.getBoundingClientRect().top:0)+bars;"
        "var delta=el.getBoundingClientRect().top-top;"
        "if(Math.abs(delta)>6){c.scrollTop=c.scrollTop+delta;}}"
        "go();(function loop(){go();if(Date.now()-t0<" + str(settle_ms) + "){requestAnimationFrame(loop);}})();"
        "}catch(e){}})();</script>",
        height=0)


_STAGE_ACTION = {
    "Detect": ("Confirm signal", "Detect", "Check the affected service and the first evidence."),
    "Triage": ("Triage & route", "Triage", "Set severity, owner and the next responsible actor."),
    "Investigate": ("Review evidence", "Investigate", "Timeline, dependency path, telemetry and change risk."),
    "Correlate": ("Confirm cause", "Correlate", "Weigh observed evidence against inferred links."),
    "Act": ("Execute fix", "Act", "Risk-gated: approval is required before execution."),
    "Verify": ("Verify now", "Verify", "The verdict here decides whether closure is possible."),
    "Close": ("Close incident", "Close", "Closure is gated on the authoritative verification."),
    "Learn": ("Capture the learning", "Learn", "What worked becomes a reusable record."),
}


def _go_stage(dom, ref, stage):
    """Primary action callback — switch the workspace to the guided view at the stage that matters,
    and land the page on that stage's section instead of leaving the reader at the top."""
    prefix = "dop" if dom == "DataOps" else "it"
    st.session_state[f"ws_mode_{ref}"] = "Act & verify (guided)"
    st.session_state[f"{prefix}_step_{ref}"] = stage
    st.session_state["_scroll_anchor"] = f"{prefix}_step_{ref}_anchor_{stage}"


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
        action_stage = "Learn"
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
                          on_click=lambda: st.session_state.update(
                              {"ws_show_gate": True, "_scroll_anchor": f"ws_gate_{ref}"}))
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

    st.query_params["inc"] = ref
    # The thread flows in the page and the identity bar pins to the top of that one scroll surface —
    # the bar is a sticky child of the app's scroll container, so there is no second scrollbar inside
    # the walkthrough. Sections carry scroll margins; actions jump to them (see _scroll_to_anchor).
    _ws_panel_css(ref)
    _collab_bar(dom, ref, you_role)
    with st.container(border=True, key=f"ws_panel_{ref}"):
        with st.container(key=f"ws_lens_{ref}"):
            _render_incident_detail(dom, ref, you_role)
        # The guided view puts the gate inside its own Close step; rendering it twice reads as a bug.
        if st.session_state.get(f"ws_mode_{ref}") != "Act & verify (guided)":
            st.divider()
            _asks = [d for d in collab.delegations(ref) if d["status"] != "done"]

            def _finish(d):
                collab.set_delegation_status(d["id"], "done", actor=d["to_"])
                st.session_state["flash"] = f'Marked done — {d["to_"]} replied on the thread (simulated).'

            with st.container(key=f"ws_gate_{ref}"):
                viz.closure_gate(journey.closure_state(inc),
                                 on_close=lambda: journey.close_incident(ref, you_role),
                                 actor=you_role, expanded=st.session_state.pop("ws_show_gate", False),
                                 asks=_asks, on_done=_finish, prefix=f"page_{ref}")

    _anchor = st.session_state.pop("_scroll_anchor", None)
    if _anchor:
        _scroll_to_anchor(_anchor)


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


# ================================================================= Analytics (v92)
def _n(n, unit="incidents", extra=""):
    """Sample-size caption. Below five samples the panel says so instead of implying significance."""
    txt = f'n={n} {unit}'
    if extra:
        txt += f' · {extra}'
    if n < analytics.MIN_SIGNIFICANT:
        txt += ' · indicative, not significant'
    return txt


def _illustrative_fallback(title, note, df=None, xf=None, yf=None, group=None):
    """The only place a scenario figure may appear: no measured data at all, and labelled twice —
    once by the badge, once in the caption. Never framed as a result or a return."""
    with st.expander(f"Illustrative — {title} (scenario estimate, not measured)", expanded=False):
        viz.data_badge("illus")
        if df is not None:
            st.altair_chart(viz.chart_bars(df, xf, yf, group=group, height=220, muted=True),
                            width="stretch")
        st.caption(f"Illustrative — {note} Not a measurement and not a benefit claim.")


def render_analytics():
    viz.page_head("Analytics — resolution performance",
                  "Every figure is measured from stored lifecycle timestamps; each panel states its "
                  "provenance and its sample size.")
    m = analytics.mttr()
    st_d = analytics.stage_durations()
    ola = analytics.ola_vs_actual()
    oc = analytics.outcomes()
    hd = analytics.handoff_delay()
    sl = analytics.sla_load()

    viz.kpi_row([
        ("MTTR · median", f'{m["median_min"]:g} min' if m["median_min"] is not None else "—",
         f'verified closures · n={m["n"]}', "#4f46e5"),
        ("MTTR · p90", f'{m["p90_min"]:g} min' if m["p90_min"] is not None else "—",
         "90th percentile of the same closures", "#6366f1"),
        ("Verified closure", f'{int(round(oc["verified_rate"] * 100))}%' if oc["verified_rate"] is not None else "—",
         f'{oc["counts"]["Verified"]} of {oc["n_records"]} resolution records', "#16a34a"),
        ("Handoff delay", f'{hd["median_min"]:g} min' if hd["median_min"] is not None else "—",
         f'request → done · n={hd["n_done"]}', "#7c3aed"),
        ("Open requests > 30 min", f'{hd["open_over_30"]}/{hd["n_open"]}',
         "coordination still waiting", "#dc2626"),
    ])
    viz.data_badge("live")
    st.caption("Computed on this system's database at page load. A dash means the data does not "
               "support the number — it is never filled with an estimate.")

    # ---------------- MTTR
    viz.section("MTTR — verified closures only",
                "raise → recorded closure, from the authoritative verification record")
    if m["closures"]:
        df = pd.DataFrame([{"Incident": c["ref"], "Minutes": c["minutes"]} for c in m["closures"]])
        st.altair_chart(viz.chart_bars(df, "Incident", "Minutes", height=220, fmt=".0f"),
                        width="stretch")
        viz.data_badge("live")
        st.caption(f'Median {m["median_min"]:g} min · p90 {m["p90_min"]:g} min · '
                   + _n(m["n"], "closures", f'{m["excluded_no_record"]} incidents with no resolution '
                                           f'record excluded, not counted as zero'))
    else:
        viz.data_badge("live")
        st.caption("No verified closure with a recorded closure time yet — MTTR is not computed. "
                   + _n(0, "closures"))

    # ---------------- stage durations + OLA
    left, right = st.columns(2)
    with left:
        viz.section("Where the time goes", "median minutes per lifecycle stage")
        rows = [r for r in st_d["rows"] if r["median_min"] is not None]
        if rows:
            df = pd.DataFrame([{"Stage": r["stage"], "Minutes": r["median_min"]} for r in rows])
            st.altair_chart(viz.chart_bars(df, "Stage", "Minutes", height=240, fmt=".0f"),
                            width="stretch")
            viz.data_badge("live")
            missing = [r["stage"] for r in st_d["rows"] if r["median_min"] is None]
            st.caption(f'{_n(st_d["n_incidents"], "incidents", "measured from " + st_d["basis"])}'
                       + (f' · no measurement yet: {", ".join(missing)}' if missing else ""))
        else:
            viz.data_badge("live")
            st.caption("No stage can be measured yet — a stage needs a recorded start and a recorded "
                       "next stage. " + _n(0, "incidents"))
    with right:
        viz.section("OLA vs actual", "stage target against the measured median")
        rows = [r for r in ola["rows"] if r["actual_min"] is not None and r["target_min"] is not None]
        if rows:
            df = pd.DataFrame([{"Stage": r["stage"], "Series": "OLA target", "Minutes": r["target_min"]}
                               for r in rows]
                              + [{"Stage": r["stage"], "Series": "Stage median", "Minutes": r["actual_min"]}
                                 for r in rows])
            df["Series"] = pd.Categorical(df["Series"], categories=["OLA target", "Stage median"],
                                          ordered=True)
            df = df.sort_values("Series")
            st.altair_chart(viz.chart_bars(df, "Stage", "Minutes", group="Series", height=240, fmt=".0f"),
                            width="stretch")
            viz.data_badge("live")
            over = [r for r in rows if r["delta_min"] is not None and r["delta_min"] > 0]
            delta_txt = " · ".join(f'{r["stage"]} {r["delta_min"]:+g} min' for r in ola["rows"]
                                   if r["delta_min"] is not None)
            thin = min(r["n"] for r in rows)
            st.caption(f'{_n(thin, "incidents in the thinnest stage", delta_txt)}'
                       + (f' · over target: {", ".join(r["stage"] for r in over)}' if over else ""))
        else:
            viz.data_badge("live")
            st.caption("No stage measured against its target yet. " + _n(0, "stages"))

    # ---------------- outcomes
    viz.section("Outcomes", "authoritative verdicts from the verification records")
    cats = ["Verified", "Mitigated", "Recovery failed", "Inconclusive"]
    df = pd.DataFrame({"Outcome": cats, "Incidents": [oc["counts"][c] for c in cats]})
    st.altair_chart(viz.chart_bars(df, "Outcome", "Incidents", height=220), width="stretch")
    viz.data_badge("live")
    st.caption(f'{_n(oc["n_records"], "resolution records", f'{oc["no_record"]} incidents without a '
                                                  f'record are uncounted, not "unresolved"')} · '
               f'verified-closure rate {int(round((oc["verified_rate"] or 0) * 100))}% of records.')

    # ---------------- learning
    lg = analytics.learning()
    mttr_l = analytics.mttr_by_learn()
    viz.section("Learning", "cause-confirmation accuracy, reuse, and time-to-resolution with a prior record")
    l1, l2, l3 = st.columns(3)
    l1.metric("Cause-confirmation accuracy", _pct(lg["accuracy"]),
              help="confirmed vs overridden, from the durable learn records")
    l1.caption(f'{lg["counts"]["confirmed"]} confirmed · {lg["counts"]["overridden"]} overridden · '
               f'{lg["counts"]["rejected"]} rejected · ' + (f'n={lg["n_decided"]} decisions'
                                                           if lg["n_decided"] else "n=0 — no decision yet"))
    l2.metric("Learn reuse", str(lg["n_reused"]) if lg["n_records"] else "—",
              help="records where a prior learn record was applied")
    l2.caption(f'applied a prior record · ' + (f'n={lg["n_records"]} records'
                                               if lg["n_records"] else "n=0 — no records yet"))
    l3.metric("MTTR · prior learn record", f'{mttr_l["with"]["median_min"]:g} min'
              if mttr_l["with"]["median_min"] is not None else "—",
              help="verified closures whose signature had a learn record saved before the incident was raised")
    l3.caption(f'with n={mttr_l["with"]["n"]} · without '
               + (f'{mttr_l["without"]["median_min"]:g} min (n={mttr_l["without"]["n"]})'
                  if mttr_l["without"]["median_min"] is not None else f'— (n={mttr_l["without"]["n"]})'))
    viz.data_badge("live")
    st.caption("A dash means the sample is empty — never zero. A learn record saved after an incident was "
               "raised is not counted as knowledge the responder had.")

    # ---------------- handoff
    viz.section("Handoff delay", "request → completion, and what is still outstanding")
    if hd["completed"]:
        df = pd.DataFrame([{"Request": f'{c["ref_id"]} · {str(c["action"])[:22]}',
                            "Minutes": c["minutes"]} for c in hd["completed"]])
        st.altair_chart(viz.chart_bars(df, "Request", "Minutes", height=220, fmt=".0f"),
                        width="stretch")
        viz.data_badge("live")
        st.caption(f'Median {hd["median_min"]:g} min · ' + _n(hd["n_done"], "completed requests",
                                                              f'{hd["n_open"]} still open, '
                                                              f'{hd["open_over_30"]} of them over 30 min'))
    elif hd["open"]:
        df = pd.DataFrame([{"Request": f'{r["ref_id"]} → {str(r["to_"])[:18]}',
                            "Minutes": r["age_min"] or 0} for r in hd["open"]])
        st.altair_chart(viz.chart_bars(df, "Request", "Minutes", height=220, fmt=".0f", muted=True),
                        width="stretch")
        viz.data_badge("live")
        st.caption(f'No request has been completed with a completion stamp yet, so there is no delay '
                   f'to report — the bars are how long each open request has been waiting, not a '
                   f'delay. {hd["open_over_30"]} of {hd["n_open"]} are older than 30 min. '
                   + _n(0, "completed requests"))
    else:
        viz.data_badge("live")
        st.caption("No collaboration request exists yet, so there is nothing to measure. "
                   + _n(0, "requests"))
        _illustrative_fallback(
            "handoff delay", "how long a request typically waits for the owning team in the "
            "scenario; the platform has no completed handoff to measure here.")

    # ---------------- SLA load
    viz.section("SLA load", "incidents per priority, split by whether the target was breached")
    hours = analytics.sla_hours()
    if sl["n"]:
        df = pd.DataFrame([{"Priority": r["priority"], "State": "Breached", "Incidents": r["breaches"]}
                           for r in sl["rows"]]
                          + [{"Priority": r["priority"], "State": "Within SLA",
                              "Incidents": r["total"] - r["breaches"]} for r in sl["rows"]])
        df["State"] = pd.Categorical(df["State"], categories=["Within SLA", "Breached"], ordered=True)
        df = df.sort_values("State")
        st.altair_chart(viz.chart_bars(df, "Priority", "Incidents", group="State", height=220),
                        width="stretch")
        viz.data_badge("live")
        per_pri = " · ".join(f'{r["priority"]} {r["breaches"]}/{r["total"]}' for r in sl["rows"])
        st.caption(f'{sl["breaches"]} breaches across {_n(sl["n"], "incidents")} · by priority {per_pri} · '
                   f'targets P1 {hours.get("P1")}h · P2 {hours.get("P2")}h · '
                   f'P3 {hours.get("P3")}h · P4 {hours.get("P4")}h · measured from the raise time to '
                   f'the recorded closure, or to now while open.')
    else:
        viz.data_badge("live")
        st.caption("No incidents on this database, so there is no SLA load to measure. "
                   + _n(0, "incidents"))
        _illustrative_fallback(
            "monthly breaches", "monthly breach totals in the scenario, in chronological order.",
            pd.DataFrame({"Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
                          "Breaches": [6, 6, 5, 4, 3, 2]}), "Month", "Breaches")

    with st.expander("How these numbers are derived", expanded=False):
        st.markdown(
            "- **MTTR** — `resolution_state.closed_at − incidents.created_at`, verdict **Verified** "
            "only. An incident without a resolution record is excluded, never treated as zero.\n"
            "- **Stage durations** — consecutive lifecycle anchors per incident: timeline events "
            "mapped by kind, stage-tagged comments, the first handoff, and the recorded closure. A "
            "stage's duration runs to the next stage's first anchor.\n"
            "- **OLA vs actual** — `stage_olas.target_min` against the measured median; delta is "
            "actual − target, so a positive number is time over the target.\n"
            "- **Outcomes** — verdict counts from the verification records; the rate's denominator is "
            "records, so an incident without one cannot inflate it.\n"
            "- **Handoff delay** — `done_at − ts` for completed requests. Requests completed before "
            "v92 have no completion stamp and are not counted as instant.\n"
            "- **SLA load** — raise → recorded closure (or now) against `personas.SLA_HOURS`.")
        st.caption("Anything the data cannot support is shown as a dash with n=0. No figure on this "
                   "page is a benefit claim.")


# ================================================================= Learn (page)
def _pct(v):
    return f'{int(round(v * 100))}%' if v is not None else "—"


def render_learn():
    viz.page_head("Learn — what worked, and where it applies",
                  "Durable records saved after closure. Each carries the confirmed cause, the steps that "
                  "actually worked, the verification outcome with who and when, and the evidence behind it.")
    recs = learn.records()
    lg = analytics.learning()
    mttr_l = analytics.mttr_by_learn()
    viz.kpi_row([
        ("Learn records", str(lg["n_records"]), "durable — survive a page reload", "#4f46e5"),
        ("Cause accuracy", _pct(lg["accuracy"]),
         f'confirmed vs overridden · n={lg["n_decided"]}' if lg["n_decided"] else "no decisions yet · n=0",
         "#16a34a"),
        ("Reuse", str(lg["n_reused"]),
         f'applied a prior record · n={lg["n_records"]}' if lg["n_records"] else "no records · n=0",
         "#7c3aed"),
        ("MTTR with prior learn",
         f'{mttr_l["with"]["median_min"]:g} min' if mttr_l["with"]["median_min"] is not None else "—",
         f'n={mttr_l["with"]["n"]} closures', "#0891b2"),
    ])
    if not recs:
        st.info("No learn records yet. Close an incident, then capture the learning in its Learn stage.")
        return
    st.caption(f'Stored at `{learn.PATH}` — outside the per-session demo database, so a reload does not '
               f'lose it.')
    groups = {}
    for r in recs:
        groups.setdefault(r.get("signature") or "unclassified", []).append(r)
    for sig, rows in sorted(groups.items(), key=lambda kv: kv[1][0].get("saved_at") or "", reverse=True):
        st.markdown(f'**Signature `{sig}`** · {len(rows)} record(s) — same component and cause class')
        for r in rows:
            title = f'{r["ref"]} · {r["title"]} · {r.get("outcome")} · {r.get("saved_at")}'
            with st.expander(title, expanded=False):
                st.markdown(f'**Root cause** — {r.get("root_cause") or "—"}')
                st.markdown(f'**Resolution summary** — {r.get("summary") or "—"}')
                st.markdown("**Steps that worked (runbook draft)**")
                for i, step in enumerate(r.get("steps") or [], 1):
                    st.markdown(f'{i}. {step}')
                st.markdown(f'**Cause verification** — {learn.OUTCOME_LABEL.get(r.get("outcome"), r.get("outcome"))} '
                            f'· {r.get("outcome_by") or "—"} · {r.get("outcome_at") or "—"}')
                if r.get("reused_from"):
                    st.markdown(f'**Reuse** — applied the fix recorded for **{r["reused_from"]}**.')
                st.markdown(f'**Evidence carried over ({len(r.get("evidence") or [])})**')
                for e in r.get("evidence") or []:
                    st.caption(f'· {e}')
                row, dom = learn.incident_row(r["ref"])
                if row and st.button(f'Open {r["ref"]} in the workspace', key=f'learn_open_{r["ref"]}'):
                    _open(dom, r["ref"])
                    st.rerun()
                elif not row:
                    st.caption("The incident this record came from is archived — the record is what survives.")


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
elif nav == "Learn":
    render_learn()
elif nav == "Analytics":
    render_analytics()
elif nav == "Activity & audit":
    render_activity()

if not st.session_state.get("open_incident"):
    st.divider()
    st.caption(f"Sample data · simulated actions · {build.label()} — proof of concept, not production. "
               "See PROTOTYPE_NOTES.md for persistence limits and TESTS.md for the test suite.")
