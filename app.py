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
        return not (v and v[0] == "v62")
    except Exception:
        return True


if _needs_seed():
    import seed  # noqa: F401

st.set_page_config(page_title="Resolution Intelligence — POC", layout="wide")
viz.inject_css()
st.title("Resolution Intelligence")
st.caption("Operational intelligence across IT Ops and DataOps — one governed platform")

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

_sv, _ed, _it_inc, _ch, _me, _G = E.load()
_dop_data = DE.load()
_dop_inc = _dop_data["incidents"]
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
            "ID": r["inc"]["id"], "Cross-domain": "🔗" if linked_map[r["inc"]["id"]] else "—",
            "Domain": r["domain"], "Title": r["inc"]["title"],
            "Status": (r["inc"].get("status") or "").title(), "Verdict": r["verdict"],
            "Stage": journey.lifecycle_stage(r["inc"]), "Owner": r["inc"].get("owner_team"),
            "SLA": (_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else "—"),
        } for r in shown])
        st.dataframe(df, hide_index=True, width="stretch")
        dom_of = {r["inc"]["id"]: r["domain"] for r in shown}
        pick = st.selectbox("Open an incident", list(dom_of), key="board_pick")
        st.button("Open incident details →", key="board_open_sel", type="primary",
                  on_click=journey._goto, args=(dom_of[pick], None, pick))
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
        st.markdown("#### 🔗 Cross-domain threads")
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


@st.dialog("🧭 Incident details", width="medium",
           on_dismiss=lambda: st.session_state.pop("open_incident", None))
def _incident_dialog(dom, ref, you_role):
    """Modal incident workspace. The board behind it never moves; sections are collapsible.
    The hero already shows the ID/domain, so the header only carries the Close control."""
    _, c2 = st.columns([6, 1])
    if c2.button("✕ Close", key="dlg_close_" + ref):
        st.session_state.pop("open_incident", None)
        st.rerun()
    _render_incident_detail(dom, ref, you_role)


def render_incidents(you_role):
    """Incident-first page: short collapsible sections on the left, a compact rail on the right."""
    main, rail = st.columns([3.4, 1])
    with main:
        with st.expander("⚡ Needs attention", expanded=True):
            _needs_attention_cards()
        with st.expander("🔗 Cross-domain resolution threads", expanded=False):
            _thread_cards("inc")
    with rail:
        with st.expander("📡 Live events", expanded=False):
            viz.feed(realtime.recent(8))
            st.caption("Simulated.")
        with st.expander("🕒 Recent activity", expanded=False):
            _recent_activity(n=8)
    with st.expander("▤ Incidents & resolution threads", expanded=True):
        render_board()
    sel = st.session_state.get("open_incident")
    if sel:
        _incident_dialog(sel["domain"], sel["ref"], you_role)


# ================================================================= Analytics
def render_analytics():
    st.subheader("Analytics — resolution performance")
    st.caption("Where a figure is derived from the sample incidents it is labelled **live data**; where "
               "it is a scenario estimate it is labelled **illustrative** — nothing is presented as a "
               "measured result unless it is.")
    incidents = list(_it_inc) + list(_dop_inc)
    verdicts = [journey.display_verdict(i) for i in incidents]
    n_open = sum(1 for i in incidents if i.get("status") == "open")
    n_verified = sum(1 for v in verdicts if v == "Verified")
    at_risk = sum(1 for i in incidents if i.get("status") == "open" and _sla_risk(i))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Incidents (total)", len(incidents))
    c2.metric("Open", n_open)
    c3.metric("Verified recoveries", n_verified)
    c4.metric("SLA at risk", at_risk)
    st.caption("**Live data** — from the current sample incidents and their authoritative verdicts.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Resolution outcomes")
        oc = ["Investigating", "Mitigated", "Verified", "Recovery failed"]
        df = pd.DataFrame({"Outcome": oc, "Incidents": [verdicts.count(v) for v in oc]}).set_index("Outcome")
        st.bar_chart(df)
        st.caption("**Live data** — authoritative verdict counts.")
    with right:
        st.markdown("#### Incidents by domain")
        dom = pd.DataFrame({
            "Domain": ["IT Ops", "DataOps"],
            "Open": [sum(1 for i in _it_inc if i.get("status") == "open"),
                     sum(1 for i in _dop_inc if i.get("status") == "open")],
            "Closed": [sum(1 for i in _it_inc if i.get("status") != "open"),
                       sum(1 for i in _dop_inc if i.get("status") != "open")],
        }).set_index("Domain")
        st.bar_chart(dom)
        st.caption("**Live data** — incident distribution across domains.")

    st.markdown("#### MTTR — baseline vs with the platform")
    mttr = pd.DataFrame({
        "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "Baseline MTTR (h)": [7.8, 7.6, 8.1, 7.9, 8.0, 7.7],
        "With platform MTTR (h)": [7.6, 6.9, 5.8, 4.6, 3.2, 2.4],
    }).set_index("Month")
    st.line_chart(mttr)
    st.caption("**Illustrative** simulated trend — MTTR falling as cross-domain correlation and "
               "coordination kick in. Measure against a real baseline in a pilot.")

    st.markdown("#### Where the time goes — baseline vs with the platform")
    steps = pd.DataFrame({
        "Step": ["Identify likely cause", "Assign next owner", "Verified recovery"],
        "Baseline (min)": [45, 30, 240],
        "With platform (min)": [10, 2, 60],
    }).set_index("Step")
    st.bar_chart(steps)
    st.caption("**Illustrative** simulated values — the acceleration the platform targets.")

    st.markdown("#### SLA / OLA breaches per month")
    br = pd.DataFrame({"Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
                       "Breaches": [6, 6, 5, 4, 3, 2]}).set_index("Month")
    st.bar_chart(br)
    st.caption("**Illustrative** simulated totals.")


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
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
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
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
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
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
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
st.caption("Sample data · simulated actions · build v74 — proof of concept, not production. "
           "See PROTOTYPE_NOTES.md for persistence limits.")
