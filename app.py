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
import liveops_view
import command_center
import viz
import journey
import collab
import shell
import workspace
import realtime


def _refresh_modules_if_stale():
    """Self-heal for Streamlit Cloud hot-reload.

    A deploy can hot-reload app.py while leaving imported sibling modules cached at an older
    build, so newly added helpers (journey.collab_stats, viz.collab_strip, …) appear missing and
    the page raises AttributeError. If we detect that, reload our own modules in place —
    importlib.reload mutates the module object, so every importer sees the refreshed attributes."""
    if all((hasattr(journey, "collab_stats"), hasattr(viz, "collab_strip"),
            hasattr(command_center, "IMPACT_ROWS"))):
        return
    for _m in (viz, journey, collab, E, DE, personas, DV, workspace, command_center, shell,
               liveops_view):
        try:
            importlib.reload(_m)
        except Exception:
            pass


_refresh_modules_if_stale()

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
        return not (v and v[0] == "v49")
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
# ---- top menu + global controls (no left bar) ----
nav, you_role = shell.topbar(_it_inc, _dop_inc, _sv, _dop_data["datasets"], _dop_data["pipelines"])
# ---- ambient live strip: global, collapsible like the overview ----
with st.expander("📡 Live — all domains", expanded=False):
    viz.ambient_strip(realtime.recent(8))


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


# ================================================================= Overview (collapsible, on the incident page)
def _overview_panel():
    dop = DE.load()
    it_open = [i for i in _it_inc if i["status"] == "open"]
    dop_open = [i for i in dop["incidents"] if i["status"] == "open"]
    at_risk = sum(1 for i in it_open + dop_open if _sla_risk(i))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("IT Ops incidents (open)", len(it_open))
    m2.metric("DataOps incidents (open)", len(dop_open))
    m3.metric("SLA at risk", at_risk)
    m4.metric("Cross-domain threads", 1)

    st.markdown("**Cross-domain resolution thread — live example**")
    viz.causal([("Schema mismatch", "DataOps"), ("Pipeline failure", "DataOps"),
                ("Stale payments data", "DataOps"), ("Payment API impact", "IT Ops")])
    corr = journey.correlation_for("INC-8841")
    st.caption(f'🔗 **INC-8841** (IT Ops) ↔ **DOP-1001** (DataOps) · shared cause '
               f'**{corr["shared_cause"] if corr else "—"}**')
    c1, c2 = st.columns(2)
    with c1:
        st.button("Open INC-8841 (IT Ops)", key="ov_it", width="stretch",
                  on_click=journey._goto, args=("IT Ops", None, "INC-8841"))
    with c2:
        st.button("Open DOP-1001 (DataOps)", key="ov_dop", width="stretch",
                  on_click=journey._goto, args=("DataOps", None, "DOP-1001"))

    st.markdown("**Live event feed — all domains**")
    f1, f2 = st.columns([1, 1])
    domf = f1.selectbox("Domain", ["All", "IT Ops", "DataOps"], key="feed_dom")
    sevf = f2.selectbox("Severity", ["All", "critical", "warning", "info"], key="feed_sev")

    def _dom(e):
        return "DataOps" if e.get("domain") == "dataops" else "IT Ops"

    events = [e for e in realtime.recent(40)
              if (domf == "All" or _dom(e) == domf) and (sevf == "All" or e.get("severity") == sevf)]
    if not events:
        st.caption("No events match the filter.")
    for e in events[:12]:
        hhmm = str(e.get("ts", "")).split("T")[-1][:5]
        label = f'{hhmm} · {_dom(e)} · {e.get("severity","")} · {e.get("source","")} — {e.get("message","")}'
        if e.get("ref_id"):
            st.button(label, key=f'feed_ev_{e.get("id")}', on_click=journey._goto,
                      args=(_dom(e), None, e["ref_id"]))
        else:
            st.markdown(f'`{hhmm}` · {_dom(e)} · {e.get("severity","")} — {e.get("message","")}')
    st.caption("Click an event to open the related incident.")

    st.markdown("**Recent activity — across all incidents**")
    rows = []
    for ref in [i["id"] for i in _it_inc] + [i["id"] for i in dop["incidents"]]:
        for cm in collab.comments(ref):
            rows.append((cm["ts"], ref, cm["author"], cm["text"]))
    rows.sort(reverse=True)
    for ts, ref, author, text in rows[:6]:
        st.markdown(f'`{ts[11:16]}` · **{ref}** · {author}  \n{text}')
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
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total incidents", len(rows))
    k2.metric("Open", n_open)
    k3.metric("Closed", len(rows) - n_open)
    k4.metric("SLA at risk", n_risk)

    f1, f2, f3, f4, f5 = st.columns([2.2, 1.1, 1.0, 1.4, 1.0])
    q = f1.text_input("Search", placeholder="id · title · owner", key="board_q")
    domf = f2.selectbox("Domain", ["All", "IT Ops", "DataOps"], key="board_dom")
    statf = f3.selectbox("Status", ["All", "Open", "Closed"], key="board_status")
    verf = f4.selectbox("Verdict", ["All"] + VERDICT_OPTIONS, key="board_verdict")
    prif = f5.selectbox("Priority", ["All", "P1", "P2", "P3"], key="board_pri")

    def _match(r):
        inc = r["inc"]
        blob = (inc["id"] + " " + inc["title"] + " " + (inc.get("owner_team") or "")).lower()
        return (not q or q.lower() in blob) \
            and (domf == "All" or r["domain"] == domf) \
            and (statf == "All" or (inc.get("status") or "").lower() == statf.lower()) \
            and (verf == "All" or r["verdict"] == verf) \
            and (prif == "All" or inc.get("priority") == prif)

    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    shown = sorted((r for r in rows if _match(r)),
                   key=lambda r: (r["inc"].get("status") != "open",
                                  order.get(r["inc"].get("priority"), 9), r["inc"]["id"]))
    st.caption(f'{len(shown)} of {len(rows)} incidents')
    if not shown:
        st.caption("No incidents match the filter.")
        return
    view = st.radio("View", ["Cards", "Table"], horizontal=True, key="board_view",
                    help="Table is easier for comparison on a wide screen; cards read better when narrow.")
    if view == "Table":
        df = pd.DataFrame([{
            "ID": r["inc"]["id"], "Domain": r["domain"], "Title": r["inc"]["title"],
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
    cols = st.columns(2)
    _open_ref = (st.session_state.get("open_incident") or {}).get("ref")
    for idx, r in enumerate(shown):
        with cols[idx % 2]:
            viz.board_card(r["inc"], r["domain"], r["verdict"],
                           on_click=journey.toggle_incident, args=(r["domain"], r["inc"]["id"]),
                           stage=journey.lifecycle_stage(r["inc"]),
                           sla=(_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else None),
                           open_=(r["inc"]["id"] == _open_ref))


def _render_incident_detail(dom, ref, you_role):
    """The selected incident's details — rendered INLINE on the incidents page."""
    lens = st.radio("View", ["Resolution thread", "Guided journey", "By role"], horizontal=True,
                    key="ws_mode_" + ref)
    if dom == "DataOps":
        data = DE.load()
        inc = next((i for i in data["incidents"] if i["id"] == ref), None)
        if inc is None:
            st.warning("Incident not found.")
            return
        if lens == "Resolution thread":
            command_center.dop_command(inc, data)
        elif lens == "Guided journey":
            DV.pipeline_view(inc, data)
        elif you_role in DV.PERSONAS:
            {"Data Engineer": DV.data_engineer_view, "Data Owner": DV.data_owner_view,
             "Platform Engineer": DV.platform_engineer_view,
             "Data Consumer": DV.data_consumer_view}[you_role](inc, data)
        else:
            st.info(f"**{you_role}** is an IT Ops role — switch the Demo persona to a DataOps role "
                    f"(Data Engineer / Data Owner / Platform Engineer / Data Consumer) to use this lens.")
    else:
        ctx = _it_ctx()
        inc = _find_it(ref)
        if inc is None:
            st.warning("Incident not found.")
            return
        if lens == "Resolution thread":
            command_center.it_command(inc, ctx)
        elif lens == "Guided journey":
            personas.incident_view(inc, ctx)
        elif you_role in personas.PERSONAS:
            {"CIO": personas.cio_view, "CSM": personas.csm_view, "Service Desk": personas.l1_view,
             "L1 Engineer": personas.l1_view, "L2 / L3 Engineer": personas.l2_view,
             "Developer": lambda i, c: personas.developer_view(c),
             "Incident Manager": personas.im_view}[you_role](inc, ctx)
        else:
            st.info(f"**{you_role}** is a DataOps role — switch the Demo persona to an IT Ops role "
                    f"(CSM / L1 / L2/L3 / Developer / Incident Manager) to use this lens.")


@st.dialog("🧭 Incident details", width="large",
           on_dismiss=lambda: st.session_state.pop("open_incident", None))
def _incident_dialog(dom, ref, you_role):
    """Modal incident workspace. The board behind it never moves; sections are collapsible."""
    c1, c2 = st.columns([5, 1])
    c1.markdown(f'**{ref}** · {dom}')
    if c2.button("✕ Close", key="dlg_close_" + ref):
        st.session_state.pop("open_incident", None)
        st.rerun()
    _render_incident_detail(dom, ref, you_role)


def render_incidents(you_role):
    """Default page. The board is the main block and never shifts; clicking a card opens the
    incident's details in a modal dialog (with collapsible sections)."""
    with st.expander("📊 Overview — at a glance", expanded=False):
        _overview_panel()
    sel = st.session_state.get("open_incident")
    if sel:
        _incident_dialog(sel["domain"], sel["ref"], you_role)
    render_board()


# ================================================================= Operations (pipelines + live signals + collaboration)
def render_operations(you_role):
    st.subheader("Operations — data & pipeline estate, and live signals")
    st.caption("The **estate and telemetry behind incidents** — pipeline/dataset health and the live "
               "signal stream. The work items themselves (all IT Ops + DataOps incidents) live in "
               "**Incidents**; there is deliberately no incident list here.")
    with st.expander("🚰 Pipelines — dataset freshness, quality and lineage", expanded=True):
        render_pipelines()
    with st.expander("📡 Live signals — event stream (Live / Replay)", expanded=False):
        render_liveops(you_role)


# ================================================================= Data & pipeline estate (no incident list — that's Incidents)
def render_pipelines():
    data = DE.load()
    st.markdown("**Dataset freshness (SLA)**")
    drows = [{"dataset": data["datasets"][ds]["name"], "layer": data["datasets"][ds]["layer"],
              "freshness": DV._fresh(data, ds)[0],
              "verdict": "🔴 breach" if DV._fresh(data, ds)[1] else "🟢 ok"}
             for ds in data["datasets"]]
    st.dataframe(pd.DataFrame(drows), hide_index=True, width="stretch")

    st.markdown("**Pipelines**")
    prows = [{"pipeline": p["name"], "owner": p["owner_team"], "criticality": p["criticality"],
              "schedule": p["schedule"], "freshness SLA": f'{p["freshness_sla_min"]} min'}
             for p in data["pipelines"].values()]
    st.dataframe(pd.DataFrame(prows), hide_index=True, width="stretch")

    st.markdown("**Data contracts**")
    crows = [{"dataset": data["datasets"][c["dataset_id"]]["name"], "contract": c["name"],
              "version": c["version"], "owner": c["owner"]} for c in data["contracts"]]
    st.dataframe(pd.DataFrame(crows), hide_index=True, width="stretch")

    st.markdown("**Lineage**")
    labels = {d: data["datasets"][d]["name"] for d in data["datasets"]}
    stale = tuple(d for d in data["datasets"] if DV._fresh(data, d)[1])
    viz.chain(["core_ledger", "ds_pay_bz", "ds_pay_sv", "ds_pay_gd"], labels, stale=stale)
    st.caption("A dataset incident is a symptom of the pipeline that produces it. Incidents are in "
               "**Incidents**; this view is the estate behind them.")


# ================================================================= Live signals (stream only — no incident queue, no collaboration)
def render_liveops(you_role):
    mode = st.radio("Stream mode", ["Live", "Replay"], horizontal=True, key="ops_live_mode")
    if mode == "Replay":
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        if c1.button("⏮ Reset", key="ops_rst"):
            realtime.clear_events()
            st.session_state["ops_ridx"] = 0
            st.session_state["ops_playing"] = False
            st.rerun()
        if c2.button("⏭ Next", key="ops_next"):
            i = st.session_state.get("ops_ridx", 0)
            if i < len(realtime.REPLAY_SCRIPT):
                realtime.emit_replay_event(realtime.REPLAY_SCRIPT[i])
                st.session_state["ops_ridx"] = i + 1
            st.rerun()
        playing = st.session_state.get("ops_playing", False)
        if c3.button("⏸ Pause" if playing else "▶ Play", key="ops_pp"):
            st.session_state["ops_playing"] = not playing
            st.rerun()
        c4.caption(f'replay step {st.session_state.get("ops_ridx", 0)}/{len(realtime.REPLAY_SCRIPT)} '
                   f'— deterministic walkthrough')
    else:
        realtime.tick()
    viz.feed(realtime.recent(14))
    st.caption("Signals are **simulated**. Owners, handoffs, comments and delegation live in each "
               "incident's workspace (open one from **Incidents**).")


# ================================================================= Analytics / Settings placeholders
def render_placeholder(name, note):
    st.subheader(name)
    st.info(f'**Placeholder — not yet implemented.** {note}')


# ================================================================= dispatch
if nav == journey.WORKSPACE_NAV:
    render_incidents(you_role)
elif nav == "Operations":
    render_operations(you_role)
elif nav == "Analytics":
    render_placeholder("Analytics", "Planned: MTTR, SLA/OLA breach trends, repeat-incident and "
                                    "resolution-confidence analytics over governed data.")

st.divider()
st.caption("Sample data · simulated actions · build v52 — proof of concept, not production. "
           "See PROTOTYPE_NOTES.md for persistence limits.")
