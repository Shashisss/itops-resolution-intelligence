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

VERDICT_OPTIONS = ["Investigating", "Mitigated", "Verified", "Recovery failed"]


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

st.set_page_config(page_title="Resolution Intelligence — POC", page_icon="assets/icon.png",
                   layout="wide")
viz.inject_css()
st.title("Resolution Intelligence")
st.caption("Operational intelligence across IT Ops and DataOps — one governed platform")

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

_sv, _ed, _it_inc, _ch, _me, _G = E.load()
_dop_data = DE.load()
_dop_inc = _dop_data["incidents"]

# ---- deep link: ?inc=<ID> opens that incident directly (a thread you can paste into a bridge call)
_deep_ref = str(st.query_params.get("inc") or "").strip()
if _deep_ref and not st.session_state.get("open_incident"):
    _deep_dom = "DataOps" if _deep_ref.upper().startswith("DOP") else "IT Ops"
    _exists = any(i["id"] == _deep_ref for i in (_it_inc if _deep_dom == "IT Ops" else _dop_inc))
    if _exists:
        st.session_state["open_incident"] = {"domain": _deep_dom, "ref": _deep_ref}
        st.session_state["nav"] = "Incidents"
# ---- left sidebar navigation (five sections) ----
nav, you_role = shell.sidebar("CSM")
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
def _needs_attention_cards(limit=4):
    """Trello-style cards for the most urgent open incidents — stage + time left at a glance."""
    dop = DE.load()
    incidents = list(_it_inc) + list(dop["incidents"])
    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    attention = sorted([i for i in incidents if i["status"] == "open"],
                       key=lambda i: (not _sla_risk(i), order.get(i["priority"], 9), i["id"]))[:limit]
    if not attention:
        st.caption("No open incidents.")
        return
    cols = st.columns(2)
    for idx, inc in enumerate(attention):
        dom = "IT Ops" if inc["id"].startswith("INC") else "DataOps"
        with cols[idx % 2]:
            viz.board_card(inc, dom, journey.display_verdict(inc), on_click=journey._goto,
                           args=(dom, None, inc["id"]), stage=journey.lifecycle_stage(inc),
                           sla=(_sla_txt(inc) if inc["status"] == "open" else None),
                           linked=bool(journey.correlation_for(inc["id"])), prefix="attn")


def _thread_cards(prefix):
    """One short card per cross-domain thread (all of them, not a single example)."""
    pairs = []
    for inc in _it_inc:
        c = journey.correlation_for(inc["id"])
        if c:
            pairs.append((inc, c))
    if not pairs:
        st.caption("No cross-domain threads in the current data.")
        return
    for inc, c in pairs:
        edges = journey.thread_edges_for(inc["id"])
        obs = sum(1 for e in edges if e["kind"] == "observed")
        inf = sum(1 for e in edges if e["kind"] == "inferred")
        with st.container(border=True):
            st.markdown(f'**{inc["id"]}** ↔ **{c["other_id"]}** · {inc["title"][:70]}')
            st.caption(f'shared cause: {c["shared_cause"]} · {obs} observed / {inf} inferred · '
                       f'verdict: {journey.display_verdict(inc)}')
            b1, b2 = st.columns(2)
            b1.button("Open IT Ops →", key=f"{prefix}_th_it_{inc['id']}", width="stretch",
                      on_click=journey._goto, args=("IT Ops", None, inc["id"]))
            b2.button("Open DataOps →", key=f"{prefix}_th_dop_{inc['id']}", width="stretch",
                      on_click=journey._goto, args=("DataOps", None, c["other_id"]))


def _recent_activity(n=6):
    dop = DE.load()
    rows = []
    for ref in [i["id"] for i in _it_inc] + [i["id"] for i in dop["incidents"]]:
        for cm in collab.comments(ref):
            rows.append((cm["ts"], ref, cm["author"], cm.get("channel", ""), cm["text"]))
    rows.sort(reverse=True)
    for ts, ref, author, ch, text in rows[:n]:
        st.markdown(f'`{ts[11:16]}` · **{ref}** · {author} · {ch or "—"} — {text[:80]}')
    if not rows:
        st.caption("No activity yet.")


# ================================================================= Incidents & resolution threads
def render_board():
    rows = ([{"inc": i, "domain": "IT Ops"} for i in _it_inc] +
            [{"inc": i, "domain": "DataOps"} for i in _dop_inc])
    for r in rows:
        r["verdict"] = journey.display_verdict(r["inc"])

    st.subheader("Incidents & resolution threads")
    st.caption("Open and closed incidents in one board. **Click a card to see its details at the top of "
               "this page** (resolution thread, impact, verification). Closed incidents read as "
               "**Verified** — closure only happens after an independently verified recovery.")

    n_open = sum(1 for r in rows if r["inc"].get("status") == "open")
    n_risk = sum(1 for r in rows if r["inc"].get("status") == "open" and _sla_risk(r["inc"]))

    def _kpi(col, label, key, **sets):
        if col.button(label, key=key, width="stretch"):
            for k, v in sets.items():
                st.session_state[k] = v

    k1, k2, k3, k4 = st.columns(4)
    _kpi(k1, f"{len(rows)}  ·  Total incidents", "kpi_total",
         board_status="All", board_verdict="All", board_risk=False)
    _kpi(k2, f"{n_open}  ·  Open", "kpi_open", board_status="Open", board_risk=False)
    _kpi(k3, f"{len(rows) - n_open}  ·  Closed", "kpi_closed", board_status="Closed", board_risk=False)
    _kpi(k4, f"{n_risk}  ·  SLA at risk", "kpi_risk", board_status="Open", board_risk=True)
    st.caption("Click a KPI card to filter. Counts are live from the current incidents.")

    f1, f2, f3, f4, f5, f6 = st.columns([2.2, 1.1, 1.0, 1.4, 1.0, 1.1])
    q = f1.text_input("Search", placeholder="id · title · owner", key="board_q")
    domf = f2.selectbox("Domain", ["All", "IT Ops", "DataOps"], key="board_dom")
    statf = f3.selectbox("Status", ["All", "Open", "Closed"], key="board_status")
    verf = f4.selectbox("Verdict", ["All"] + VERDICT_OPTIONS, key="board_verdict")
    prif = f5.selectbox("Priority", ["All", "P1", "P2", "P3"], key="board_pri")
    risk_only = f6.checkbox("SLA at risk", key="board_risk")

    def _reset_filters():
        for k, v in (("board_q", ""), ("board_dom", "All"), ("board_status", "All"),
                     ("board_verdict", "All"), ("board_pri", "All"), ("board_risk", False)):
            st.session_state[k] = v

    active = []
    if q:
        active.append(f"search: {q}")
    if domf != "All":
        active.append(f"domain: {domf}")
    if statf != "All":
        active.append(f"status: {statf}")
    if verf != "All":
        active.append(f"verdict: {verf}")
    if prif != "All":
        active.append(f"priority: {prif}")
    if risk_only:
        active.append("SLA at risk")
    if active:
        st.markdown(" ".join(f'<span class="ri-tag" style="background:#4f46e5">{c}</span>' for c in active),
                    unsafe_allow_html=True)
        st.button("Reset filters", key="board_reset", on_click=_reset_filters)

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
    st.caption(f'{len(shown)} of {len(rows)} incidents')
    if not shown:
        st.caption("No incidents match the filters.")
        st.button("Clear filters", key="board_clear", on_click=_reset_filters)
        return
    view = st.radio("View", ["Cards", "Table"], horizontal=True, key="board_view",
                    help="Table is easier for comparison on a wide screen; cards read better when narrow.")
    linked_map = {r["inc"]["id"]: bool(journey.correlation_for(r["inc"]["id"])) for r in shown}
    if view == "Table":
        df = pd.DataFrame([{
            "ID": r["inc"]["id"], "Cross-domain": "Yes" if linked_map[r["inc"]["id"]] else "—",
            "Severity": f'{viz.SEV_LABEL.get(r["inc"].get("priority"), ("", "Minor"))[1]}',
            "Priority": r["inc"].get("priority"),
            "Domain": r["domain"], "Title": r["inc"]["title"],
            "Status": (r["inc"].get("status") or "").title(), "Verdict": r["verdict"],
            "Stage": journey.lifecycle_stage(r["inc"]), "Owner": r["inc"].get("owner_team"),
            "SLA": (_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else "—"),
        } for r in shown])
        ev = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun",
                          selection_mode="single-row", key="board_table")
        st.caption("Click a row to open that incident.")
        try:
            _rows = list(ev.selection["rows"])
        except Exception:
            _rows = []
        if _rows:
            r = shown[_rows[0]]
            journey.toggle_incident(r["domain"], r["inc"]["id"])
            st.rerun()
        return

    _open_ref = (st.session_state.get("open_incident") or {}).get("ref")

    def _render_cards(subset):
        cols = st.columns(2)
        for idx, r in enumerate(subset):
            with cols[idx % 2]:
                viz.board_card(r["inc"], r["domain"], r["verdict"],
                               on_click=journey.toggle_incident, args=(r["domain"], r["inc"]["id"]),
                               stage=journey.lifecycle_stage(r["inc"]),
                               sla=(_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else None),
                               open_=(r["inc"]["id"] == _open_ref),
                               linked=linked_map[r["inc"]["id"]])

    cross = [r for r in shown if linked_map[r["inc"]["id"]]]
    single = [r for r in shown if not linked_map[r["inc"]["id"]]]
    if cross:
        st.markdown("#### Cross-domain threads")
        st.caption("IT Ops and DataOps incidents resolved together as one governed thread.")
        _render_cards(cross)
    if single:
        st.markdown("#### Single-domain incidents")
        st.caption("Independent IT Ops or DataOps incidents.")
        _render_cards(single)


def _render_incident_detail(dom, ref, you_role):
    """The selected incident's details — rendered in the incident dialog."""
    lens = st.radio("View", ["Resolution thread", "Guided journey"], horizontal=True,
                    key="ws_mode_" + ref)
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


@st.dialog("Incident details", width="medium",
           on_dismiss=lambda: st.session_state.pop("open_incident", None))
def _incident_dialog(dom, ref, you_role):
    """Modal incident workspace. The board behind it never moves; sections are collapsible.
    The hero already shows the ID/domain, so the header only carries the Close control."""
    _, c2, c3 = st.columns([5.0, 1.1, 0.8])
    with c2:
        with st.popover("Share", width="stretch"):
            st.caption("Stable link to this thread — append to the app URL.")
            st.code(f'?inc={ref}', language=None)
    if c3.button("Close", key="dlg_close_" + ref, width="stretch"):
        st.session_state.pop("open_incident", None)
        st.rerun()
    _render_incident_detail(dom, ref, you_role)


def render_incidents(you_role):
    """Incident-first page: short collapsible sections on the left, a compact rail on the right."""
    main, rail = st.columns([3.15, 1.15])
    with main:
        with st.expander("Needs attention", expanded=True):
            _needs_attention_cards()
        with st.expander("Cross-domain resolution threads", expanded=False):
            _thread_cards("inc")
    with rail:
        with st.expander("Live events", expanded=False):
            viz.feed(realtime.recent(8))
            st.caption("Simulated.")
        with st.expander("Recent activity", expanded=False):
            _recent_activity(n=8)
    with st.expander("Incidents & resolution threads", expanded=True):
        render_board()
    sel = st.session_state.get("open_incident")
    if sel:
        st.query_params["inc"] = sel["ref"]
        _incident_dialog(sel["domain"], sel["ref"], you_role)
    elif "inc" in st.query_params:
        del st.query_params["inc"]


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
    render_incidents(you_role)
elif nav == "Analytics":
    render_analytics()
elif nav == "Activity & audit":
    render_activity()

st.divider()
st.caption("Sample data · simulated actions · build v76 — proof of concept, not production. "
           "See PROTOTYPE_NOTES.md for persistence limits.")
