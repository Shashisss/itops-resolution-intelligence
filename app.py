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
import graph
import graph_views
import shell
import story
import ask
import ask_view
import agents
import sections
import panel
import workspace
import realtime
import runclock


_RELOAD_TARGETS = (viz, journey, collab, analytics, learn, E, DE, personas, DV, workspace,
                   command_center, shell, realtime, graph, graph_views, story, ask, ask_view, agents, sections, panel)


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
runclock.begin()   # one clock for this render — no 60m beside 61m for the same fact

# Every browser session gets its own copy of the demo database: actions, verifications and closures
# are real inside the session and gone after a refresh. Set RI_DEMO_MODE=0 to persist.
_DB_PATH = store.db()
for _mod in (E, DE, journey, collab, analytics, realtime):
    _mod.DB = _DB_PATH
learn.DB = _DB_PATH          # learn records live outside the session copy on purpose (durable)
graph.DB = _DB_PATH          # the views read the graph, not the flat tables
story.DB = _DB_PATH          # one definition for every number the story layer states
ask.DB = _DB_PATH            # the Ask box executes against this session's copy
with st.spinner("Building the connection graph for this session…"):
    _GRAPH_INFO = graph.ensure(_DB_PATH)   # idempotent projection — an older database gains the graph
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
        st.session_state["nav"] = journey.WORKSPACE_NAV
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
if not st.session_state.get("open_incident"):
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
    s = story.sla(i)
    if s["closed"] or s["target_hours"] is None:
        return False
    return (s["remaining_min"] or 0) < s["target_hours"] * 60 * 0.5


def _sla_txt(i):
    """The SLA clock — story.sla() is the only definition of it (hero strip, identity bar, list)."""
    return story.sla(i)["text"]


# ================================================================= The incident (one scroll)
def _render_incident_detail(dom, ref, you_role):
    """The incident itself: thread, actions, close gate and learn record in one scroll.

    v99 removed the thread/guided switch. Two lenses meant the person had to decide how to read
    before reading, and the actions hid behind one of them. Every stage keeps its section anchor,
    so the primary action still lands the page on the step it names."""
    if dom == "DataOps":
        data = DE.load()
        inc = next((i for i in data["incidents"] if i["id"] == ref), None)
        if inc is None:
            st.warning("Incident not found.")
            return
        DV.pipeline_view(inc, data)
    else:
        ctx = _it_ctx()
        inc = _find_it(ref)
        if inc is None:
            st.warning("Incident not found.")
            return
        personas.incident_view(inc, ctx)


ACT_STAGES = [("Correlate", "Confirm cause"), ("Act", "Apply remediation"),
              ("Verify", "Run verification"), ("Close", "Close")]


def _stage_functions(dom, ref, inc):
    """The stage bodies for this domain, so the Act & verify tab can render one at a time."""
    if dom == "DataOps":
        return DV.stage_functions(inc, DE.load())
    ctx = _it_ctx()
    return personas.incident_sections(inc, ctx)


def _act_tab(dom, ref, inc, you_role):
    """Act & verify — the only uncapped tab, bounded by construction: one stage at a time."""
    fns = _stage_functions(dom, ref, inc)
    names = dict(ACT_STAGES)
    sel = st.session_state.get(f"act_stage_{ref}")
    if sel not in names:
        cur = journey.lifecycle_stage(inc)
        sel = cur if cur in names else "Act"
        st.session_state[f"act_stage_{ref}"] = sel
    viz.phase_stepper(journey.lifecycle_stage(inc))
    cols = st.columns(len(ACT_STAGES))
    for (stage, label), col in zip(ACT_STAGES, cols):
        if col.button(label, key=f"act_{ref}_{stage}", width="stretch",
                      type=("primary" if stage == sel else "secondary")):
            st.session_state[f"act_stage_{ref}"] = stage
            st.rerun()
    prefix = "dop" if dom == "DataOps" else "it"
    with st.container(key=f"{prefix}_step_{ref}_anchor_{sel}"):
        fns[sel]()


def _next_ask(inc):
    """The ask behind the next action, in the requester's words — distinct from the button label."""
    asks = [d for d in collab.delegations(inc["id"]) if d.get("status") != "done"]
    if not asks:
        return ""
    oldest = min(asks, key=lambda d: d.get("ts") or "")
    return (oldest.get("action") or "").split(" · expected in")[0]


def _tab_body(name, dom, ref, inc, you_role):
    """Everything that is not the header, the tiles or a tab header."""
    if name == "Timeline":
        journey.render_timeline(ref, limit=3)
    elif name == "Requests":
        _collab_bar(dom, ref, you_role, heading=False)
    elif name == "Evidence & RCA":
        _agent_panel(dom, ref, inc)
        corr = journey.correlation_for(ref)
        if corr:
            st.caption(f'Shared cause with {corr["other_domain"]} {corr["other_id"]}: '
                       f'{corr["shared_cause"]}')
        ev = story.evidence(inc, limit=99)
        for item in ev[:3]:
            st.markdown(f'- {item}')

    elif name == "Connections & audit":
        graph_views.connections_panel(ref, key=f"conn_{ref}")
        _accel_strip(inc)
        activity_section(ref)
    elif name == "Act & verify":
        _act_tab(dom, ref, inc, you_role)
    elif name == "Learn":
        learn.panel(inc, "DataOps" if dom == "DataOps" else "IT Ops", actor=you_role)


def _preview(dom, ref):
    """v106: selecting a row shows the drawer; opening is one deliberate click from there."""
    st.session_state["board_preview"] = {"domain": dom, "ref": ref}


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


def _collaborate_popover(dom, ref, inc, you_role):
    """Ask someone for something specific, with a deadline — logged on the thread, never sent."""
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


def _collab_bar(dom, ref, you_role, heading=True):
    """Requests, with the people on the thread and one obvious way to ask for something.

    v106: the people line and the two controls live in the section header, not in a row of their own."""
    inc = _find_dop(ref) if dom == "DataOps" else _find_it(ref)
    if inc is None:
        return

    def _controls():
        c2, c3 = st.columns([1.55, 0.85], vertical_alignment="center")
        with c2:
            _collaborate_popover(dom, ref, inc, you_role)
        with c3:
            with st.popover("Share", width="stretch"):
                st.caption("Stable link to this thread.")
                st.code(f'?inc={ref}', language=None)

    _people = _participants(inc)
    _on_it = "on it — " + " · ".join(_people[:3]) + (f" +{len(_people) - 3}" if len(_people) > 3 else "")
    if heading:
        viz.section("Requests", _on_it, right=_controls)
    else:
        st.caption(_on_it)
        _controls()
    cards = story.requests(ref)
    open_cards = [c for c in cards if c["status"] != "done"]
    done_cards = [c for c in cards if c["status"] == "done"]
    impact_txt = story.impact(inc)["text"]
    ev = story.evidence(inc)
    if open_cards:
        for c in open_cards:
            cols = st.columns([5.55, 1.55], vertical_alignment="center")
            with cols[0]:
                viz.request_card(c, (c["stage"], impact_txt, ev[-1] if ev else "—"), key=c["id"])
            with cols[1]:
                # one action per reader: chase it, or (as the owner) move its state
                b1, b2 = (st.container(), st.container())
                if b1.button("Chase", key=f"ask_chase_{c['id']}", width="stretch", type="primary"):
                    collab.add_comment(ref, you_role, "Person",
                                       f'Chased {c["owner"]} for: {c["ask"]} (simulated)')
                    st.session_state["flash"] = f'Reminder logged to {c["owner"]} (simulated).'
                    st.rerun()
                if c["status"] == "assigned":
                    if b2.button("Acknowledge", key=f"ask_ack_{c['id']}", width="stretch",
                                 type="tertiary", help=f'As {c["owner"]} (simulated)'):
                        collab.set_delegation_status(c["id"], "accepted", actor=c["owner"])
                        collab.add_comment(ref, c["owner"], "Person",
                                           f'Acknowledged: {c["ask"]} (simulated)')
                        st.session_state["flash"] = f'Acknowledged by {c["owner"]} on the thread (simulated).'
                        st.rerun()
                elif c["status"] in ("accepted", "reopened"):
                    if b2.button("Answered", key=f"ask_done_{c['id']}", width="stretch",
                                 type="tertiary", help=f'As {c["owner"]} (simulated)'):
                        collab.set_delegation_status(c["id"], "done", actor=c["owner"])
                        collab.add_comment(ref, c["owner"], "Person", f'Done: {c["ask"]} (simulated)')
                        st.session_state["flash"] = f'Marked answered — {c["owner"]} replied (simulated).'
                        st.rerun()
    else:
        st.caption("No open request — nobody is holding this. Use **Collaborate** to ask someone, "
                   "with a deadline.")
    if done_cards:
        with st.expander(f"Answered · {len(done_cards)}", expanded=False):
            for d in [x for x in collab.delegations(ref) if x["status"] == "done"]:
                c = st.columns([6, 1], vertical_alignment="center")
                c[0].markdown(f'~~{d["to_"]} · {d["action"]}~~', unsafe_allow_html=True)
                if c[1].button("Reopen", key=f"ask_reopen_{d['id']}", width="stretch"):
                    collab.set_delegation_status(d["id"], "reopened", actor=you_role)
                    collab.add_comment(ref, you_role, "Person",
                                       f'Reopened the request to {d["to_"]}: {d["action"]} (simulated)')
                    st.session_state["flash"] = f'Reopened the request to {d["to_"]} (simulated).'
                    st.rerun()


def _agent_panel(dom, ref, inc):
    """Who's on it — static definition, live numbers. Undefined incidents get a neutral empty state
    rather than an invented panel."""
    p = agents.panel(inc)
    if not p:
        viz.section("Who's on it", "no agent definition for this incident")
        st.caption("Nothing is defined for this incident — the record above is unchanged. The panel "
                   "is a static per-incident definition and never invents a team.")
        return
    viz.agent_panel_head(p)
    c = st.columns([1.5, 4.5], vertical_alignment="center")
    c[0].button("See the ranked list →", key=f"agents_ranked_{ref}", width="stretch",
                on_click=_go_stage, args=(dom, ref, "Correlate"),
                help="Lands on the Correlate section, where the ranked leads are rendered.")
    viz.agent_panel_tail(p)
    controls = st.columns([1, 1, 1, 3.6], vertical_alignment="center")
    for i, label in enumerate(("Approve", "Edit", "Reject")):
        controls[i].button(label, key=f"agents_{label.lower()}_{ref}", width="stretch",
                           disabled=True)
    controls[3].caption("Inert in this POC — the draft is never sent, so these stay disabled "
                        "rather than pretending to work.")


def _extra_sections(dom, ref, inc):
    """The sections that fold away below the lifecycle: the agent panel, connections, evidence,
    activity and the record. Each header states what is inside; opening one closes the stage."""
    opened = st.session_state.get(f"open_{ref}")
    with st.container(key=f"acc_group_{ref}_extras"):
        for r in sections.extra_rows(inc, dom):
            with st.container(key=f"extra_{ref}_{r['key']}"):
                viz.accordion_header(ref, r["key"], r["title"], detail=r["fact"],
                                     badge=r["badge"], is_open=(opened == r["key"]))
                if opened != r["key"]:
                    continue
                if r["key"] == "agents":
                    _agent_panel(dom, ref, inc)
                elif r["key"] == "connections":
                    graph_views.connections_panel(ref, key=f"conn_{ref}")
                elif r["key"] == "evidence":
                    ev = story.evidence(inc, limit=99)
                    if ev:
                        for item in ev:
                            st.markdown(f'- {item}')
                    else:
                        st.caption("No evidence recorded on the thread.")
                elif r["key"] == "activity":
                    activity_section(ref)
                elif r["key"] == "record":
                    sections.record_body(inc, dom)


def _core_strip(dom, ref, inc):
    """The first three seconds of the incident: who holds it, the SLA clock, how far the work has
    crossed. One definition each (story.py), one line each, no decoration — the handoff path and
    the measured acceleration sit directly under it so the numbers and the picture agree."""
    h = story.hero(inc)
    viz.hero_strip(h["facts"])
    viz.domain_chain(h["cross"]["nodes"])
    corr = journey.correlation_for(ref)
    if corr:
        st.caption(f'Shared cause with {corr["other_domain"]} {corr["other_id"]}: {corr["shared_cause"]}')


def _accel_strip(inc):
    """Acceleration, measured — never estimated. A number the record cannot support is an em dash."""
    a = story.acceleration(inc)
    viz.accel_row([
        ("Time to next action", story.fmt_minutes(a["time_to_next_action_min"]),
         f'from the alarm to the first recorded action — {a["time_to_next_action_what"]}'
         if a["time_to_next_action_min"] is not None else "no action recorded yet"),
        ("Unblocked by evidence", story.fmt_minutes(a["unblocked_by_evidence_min"]),
         f'{a["holder"]} asked → {a["unblocked_by_evidence_what"]}'
         if a["unblocked_by_evidence_min"] is not None else "no evidence recorded after the request"),
    ])


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
    st.session_state[f"tab_{ref}"] = "Act & verify"      # v107: the promoted action lands in tab 5
    st.session_state[f"act_stage_{ref}"] = stage
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

    refs = _all_refs()
    idx = next((n for n, (_d, i) in enumerate(refs) if i["id"] == ref), None)
    queue = f'{idx + 1} of {len(refs)} in the queue' if idx is not None else ""

    with st.container(key=f"ws_head_{ref}"):
        _bc, _tt = st.columns([1.45, 8.55], vertical_alignment="center")
        with _bc:
            st.button("All incidents", key="ws_back", on_click=_close_workspace,
                      type="tertiary")
        with _tt:
            panel.header(inc, verdict, sev, queue, "closed" if closed else sla)

    st.query_params["inc"] = ref
    _ws_panel_css(ref)
    panel.tiles(inc)

    _left, _right = st.columns([1.62, 1], gap="small")
    with _left:
        panel.graph_card(inc)
    with _right:
        panel.meaning_card(inc, _next_ask(inc) or action_label, None)
        if action_label:
            if action_stage == "Close" and gate["eligible"]:
                st.button(action_label, type="primary", width="stretch", key="ws_primary",
                          on_click=_close_now, args=(ref, you_role))
            elif action_stage == "Close":
                st.button("See the blockers", width="stretch", key="ws_primary",
                          on_click=_go_stage, args=(dom, ref, "Close"))
            else:
                st.button(action_label, type="primary", width="stretch", key="ws_primary",
                          on_click=_go_stage, args=(dom, ref, action_stage), help=action_why)
        panel.who_card(inc, _participants(inc))

    # Deep links: ?tab=… selects a tab, ?step=… lands in Act & verify at that stage,
    # ?expand=… opens the tab that now carries that section. Applied once per distinct value.
    _tab = (st.query_params.get("tab") or "").strip()
    _step = (st.query_params.get("step") or "").strip()
    _expand = (st.query_params.get("expand") or "").strip()
    _token = f"{_tab}|{_step}|{_expand}"
    if (_tab or _step or _expand) and st.session_state.get(f"deep_{ref}") != _token:
        st.session_state[f"deep_{ref}"] = _token
        _stage = _step.title().replace("_", " ")
        if _stage in journey.LIFECYCLE:
            st.session_state[f"tab_{ref}"] = "Act & verify"
            st.session_state[f"act_stage_{ref}"] = _stage
        elif _expand in ("agents", "evidence"):
            st.session_state[f"tab_{ref}"] = "Evidence & RCA"
        elif _expand in ("connections", "activity", "record"):
            st.session_state[f"tab_{ref}"] = "Connections & audit"

    st.session_state[f"tabstate_{ref}"] = panel.tab_state(inc, dom)
    active = panel.active_tab(ref, default="Timeline")
    panel.tab_bar(ref, active)
    if active == "Act & verify":
        st.markdown(f'<style>.st-key-tabbody_{ref}{{max-height:none;overflow:visible}}'
                    f'.st-key-ws_panel_{ref}{{border:none;padding:0}}</style>', unsafe_allow_html=True)
    with st.container(key=f"ws_panel_{ref}"):
        with st.container(key=f"tabbody_{ref}"):
            _tab_body(active, dom, ref, inc, you_role)
    if active in ("Timeline", "Evidence & RCA", "Connections & audit", "Requests"):
        _sp, _sa = st.columns([6.6, 1.4], vertical_alignment="center")
        _sp.caption(f"Showing the first screen of {active.lower()} — the rest is in the full view.")
        if _sa.button(f"Show all · {active}", key=f"showall_{ref}", width="stretch"):
            panel.full_view(active, dom, ref, inc, you_role)

    _anchor = st.session_state.pop("_scroll_anchor", None)
    if _anchor:
        _scroll_to_anchor(_anchor)


def _queue_line(inc):
    """One secondary line that answers the queue questions before the click.

    holder and how long · SLA left · cross-domain or not · the next action."""
    ref = inc["id"]
    w, s, c = story.waiting(inc), story.sla(inc), story.cross(inc)
    bits = [f'{w["who"]} holds {story.fmt_minutes(w["minutes"])}' if not w["empty"]
            else "nobody is holding it"]
    bits.append(s["text"] if (inc.get("status") or "").lower() != "closed" else "closed")
    # cross-domain means the thread is linked to the other domain — not merely "two labels in the
    # chain" (origin service + owning team is still one domain).
    bits.append("cross-domain" if journey.correlation_for(ref) else "single-domain")
    nxt = journey.next_action(inc, journey.lifecycle_stage(inc))
    if nxt.get("label"):
        bits.append(f'next: {nxt["label"]}')
    return "  ·  ".join(bits)


def _drawer(dom, ref, you_role):
    """Right-hand summary: the hero facts for the selected incident, and one way in."""
    inc = _find_dop(ref) if dom == "DataOps" else _find_it(ref)
    if inc is None:
        return
    w, s, c = story.waiting(inc), story.sla(inc), story.cross(inc)
    nxt = journey.next_action(inc, journey.lifecycle_stage(inc))
    facts = [
        ("Waiting", w["text"] if not w["empty"] else "No open request", "oldest open request"),
        ("SLA left", s["text"], f'{s["target_hours"]}h target · {inc.get("priority")}'),
        ("Cross-domain", c["text"], " · ".join(n["label"] for n in c["nodes"])),
        ("Blocker", inc.get("blocker") or "—", inc.get("owner_team") or ""),
        ("Next actor", nxt.get("label") or "—", nxt.get("why") or ""),
    ]
    viz.drawer(inc, dom, journey.display_verdict(inc), facts, nxt, inc.get("blocker"),
               on_open=_open_from_drawer)


def _open_from_drawer(dom, ref):
    st.session_state.pop("board_preview", None)
    _open(dom, ref)


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
    ask_view.render("ask_inc", "Ask — how many incidents were reported yesterday")

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

    sel = st.session_state.get("board_preview")
    body = st.columns([2.35, 1], gap="large") if sel else None
    with (body[0] if body else st.container()):
        if view == "List":
            for r in shown:
                viz.list_row(r["inc"], r["domain"], r["verdict"], on_click=_preview,
                             args=(r["domain"], r["inc"]["id"]), stage=journey.lifecycle_stage(r["inc"]),
                             secondary=_queue_line(r["inc"]))
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
    if body:
        with body[1]:
            _drawer(sel["domain"], sel["ref"], you_role)

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
    ask_view.render("ask_an", "Ask — what is our median resolution time this week")
    _wk = (dt.datetime.now() - dt.timedelta(days=6)).replace(hour=0, minute=0, second=0,
                                                             microsecond=0)
    _created = analytics.created_between(_wk.isoformat(timespec="seconds"), None)
    st.caption(f'Definitions on this page: {_created["n"]} incidents created in the last 7 days of '
               f'{_created["checked"]} on record · MTTR from verified closures only · handoffs from '
               f'delegations. The Ask box answers with these same functions.')
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
        latest = sorted(rows, key=lambda r: r.get("saved_at") or "", reverse=True)[0]
        viz.inherit_block(story.inheritance(latest))
        _row, _dom = learn.incident_row(latest["ref"])
        if _row and st.button(f'Open {latest["ref"]} — the incident this came from',
                              key=f'inherit_open_{latest["ref"]}'):
            _open(_dom, latest["ref"])
            st.rerun()
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


def render_agents():
    """The fleet on one page: one agent is live, five are design. No orchestration engine."""
    viz.page_head("Agents — who acted, and what they may do",
                  "One agent is live (RCA ranking over stored signals). The other five are design "
                  "rows, labelled as such. No agent executes a change, sends a message or closes an "
                  "incident.")
    rows = agents.agents()
    live = sum(1 for a in rows if "live" in str(a.get("status")).lower())
    viz.kpi_row([
        ("Agents defined", str(len(rows)), "static rows — not a running fleet", "#4f46e5"),
        ("Live", str(live), "RCA ranking · reads stored signals", "#16a34a"),
        ("Design", str(len(rows) - live), "no code path, stated as design", "#64748b"),
    ])
    for a in rows:
        is_live = "live" in str(a.get("status")).lower()
        chip = (f'<span class="ri-simchip" style="border-color:#86efac;color:#166534;'
                f'background:#f0fdf4">{a["status"]}</span>' if is_live else
                f'<span class="ri-simchip" style="border-color:#cbd5e1;color:#64748b;'
                f'background:#f8fafc">{a["status"]}</span>')
        st.markdown(
            f'<div class="ri-ablock"><div class="d">{a["name"]} {chip}</div>'
            f'<div class="s">{a["allowed"]}</div></div>', unsafe_allow_html=True)
    st.caption("This page is a definition list, not a control plane. The incident panel names the "
               "agent that acted and the evidence it used.")


# ================================================================= Activity & audit (page)
def activity_section(ref=None, heading=True):
    """Activity & audit as a section of the incident screen (v99 folded the page in here).

    `ref` scopes it to one incident; without it the section covers the whole board."""
    if heading:
        st.markdown("**Activity & audit** — actions, handoffs, verification records")
    st.caption("Persisted records from the current data (sample).")
    refs = [ref] if ref else [i["id"] for i in _it_inc] + [i["id"] for i in _dop_inc]
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
        st.caption("No incident is open — pick one from the list.")
        render_incidents(you_role)
elif nav == "Incidents":
    render_incidents(you_role)
elif nav == "Learn":
    render_learn()
elif nav == "Agents":
    render_agents()
elif nav == "Analytics":
    render_analytics()


if not st.session_state.get("open_incident"):
    st.divider()
    _bi = build.info()
    st.caption(f'Sample data · simulated actions · build {_bi["build"]} · commit {_bi["sha"]}'
               + (f' · {_bi["time"]}' if _bi["time"] else '')
               + " — proof of concept, not production. See PROTOTYPE_NOTES.md for persistence "
                 "limits and TESTS.md for the test suite.")
