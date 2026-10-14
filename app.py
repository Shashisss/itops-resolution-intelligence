#!/usr/bin/env python3
"""Resolution Intelligence — Streamlit POC.
One governed platform across IT Ops and DataOps.
Unified shell · one incident workspace · one lifecycle · one status vocabulary.
Deterministic graph + rule-based reasoning. SAMPLE DATA · SIMULATED ACTIONS."""
import os
import datetime as dt
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
        con.close()
        return False
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
_dop_inc = DE.load()["incidents"]
# ---- top menu + global controls (no left bar) ----
nav, you_role = shell.topbar(_it_inc, _dop_inc)


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


# ================================================================= Overview
def render_overview():
    dop = DE.load()
    it_open = [i for i in _it_inc if i["status"] == "open"]
    dop_open = [i for i in dop["incidents"] if i["status"] == "open"]
    at_risk = sum(1 for i in it_open + dop_open if _sla_risk(i))
    st.subheader("Overview — one workspace across IT Ops and DataOps")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("IT Ops incidents (open)", len(it_open))
    m2.metric("DataOps incidents (open)", len(dop_open))
    m3.metric("SLA at risk", at_risk)
    m4.metric("Cross-domain threads", 1)
    st.caption("Start from **Incidents & resolution threads** to open any incident's workspace.")

    st.markdown("#### Cross-domain resolution thread — live example")
    viz.causal([("Schema mismatch", "DataOps"), ("Pipeline failure", "DataOps"),
                ("Stale payments data", "DataOps"), ("Payment API impact", "IT Ops")])
    corr = journey.correlation_for("INC-8841")
    st.caption(f'🔗 **INC-8841** (IT Ops) ↔ **DOP-1001** (DataOps) · shared cause '
               f'**{corr["shared_cause"] if corr else "—"}**')
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Open INC-8841 (IT Ops)", key="ov_it", use_container_width=True,
                     on_click=journey._goto, args=("IT Ops", None, "INC-8841")):
            pass
    with c2:
        if st.button("Open DOP-1001 (DataOps)", key="ov_dop", use_container_width=True,
                     on_click=journey._goto, args=("DataOps", None, "DOP-1001")):
            pass

    st.markdown("#### Recent activity — across all incidents")
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
    st.caption("Open and closed incidents in one board. **Click a card to open its workspace** "
               "(the resolution thread). Closed incidents read as **Verified** — closure only happens "
               "after an independently verified recovery. Verdicts are session-scoped and reset on restart.")

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
    cols = st.columns(2)
    for idx, r in enumerate(shown):
        with cols[idx % 2]:
            viz.board_card(r["inc"], r["domain"], r["verdict"],
                           on_click=journey._goto, args=(r["domain"], None, r["inc"]["id"]),
                           stage=journey.lifecycle_stage(r["inc"]),
                           sla=(_sla_txt(r["inc"]) if r["inc"].get("status") == "open" else None))


def render_incidents(you_role):
    sel = st.session_state.get("open_incident")
    if not sel:
        render_board()
        return
    ref, dom = sel["ref"], sel["domain"]
    if st.button("← All incidents", key="back_board"):
        st.session_state.pop("open_incident", None)
        st.rerun()
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
            {"CSM": personas.csm_view, "L1 Engineer": personas.l1_view, "L2 / L3 Engineer": personas.l2_view,
             "Developer": lambda i, c: personas.developer_view(c),
             "Incident Manager": personas.im_view}[you_role](inc, ctx)
        else:
            st.info(f"**{you_role}** is a DataOps role — switch the Demo persona to an IT Ops role "
                    f"(CSM / L1 / L2/L3 / Developer / Incident Manager) to use this lens.")


# ================================================================= Operations (pipelines + live signals + collaboration)
def render_operations(you_role):
    st.subheader("Operations — pipelines, dependencies and live signals")
    st.caption("The DataOps signals and dependencies that explain incidents, plus the live event feed and "
               "cross-domain collaboration.")
    t1, t2, t3 = st.tabs(["Pipelines", "Live signals", "Collaboration"])
    with t1:
        render_pipelines()
    with t2:
        render_liveops(you_role)
    with t3:
        render_collab()


# ================================================================= Data pipelines
def render_pipelines():
    data = DE.load()
    st.subheader("Data pipelines — freshness, quality and lineage")
    st.markdown("#### Dataset freshness (SLA)")
    drows = []
    for ds in data["datasets"]:
        ft, breach, lag, sla = DV._fresh(data, ds)
        drows.append({"dataset": data["datasets"][ds]["name"], "layer": data["datasets"][ds]["layer"],
                      "freshness": ft, "status": "🔴 breach" if breach else "🟢 ok"})
    viz.card_rows(drows, "#0d9488")
    st.markdown("#### Pipeline incidents")
    statf = st.selectbox("Status", ["All", "Open", "Closed"], key="pipe_status")
    for inc in data["incidents"]:
        if statf != "All" and (inc.get("status") or "").lower() != statf.lower():
            continue
        viz.board_card(inc, "DataOps", journey.display_verdict(inc),
                       on_click=journey._goto, args=("DataOps", None, inc["id"]))


# ================================================================= Live operations
def render_liveops(you_role):
    name = st.text_input("Your name", value="You", key="lo_name")
    liveops_view.render(name, you_role)


# ================================================================= Collaboration & activity
def render_collab():
    st.subheader("Collaboration & activity — across all incidents")
    refs = [i["id"] for i in _it_inc] + [i["id"] for i in _dop_inc]
    st.markdown("#### Recent updates")
    items = []
    for r in refs:
        for c in collab.comments(r):
            items.append((c["ts"], r, c["author"], c["role"], c["text"]))
    items.sort(reverse=True)
    for ts, r, author, role, text in items[:30]:
        st.markdown(f'`{ts[11:19]}` · **{r}** · {author} ({role})  \n{text}')
    if not items:
        st.caption("No updates yet.")
    st.markdown("#### Open delegations & handoffs")
    open_deleg = [(r, d) for r in refs for d in collab.delegations(r) if d["status"] != "done"]
    if open_deleg:
        for r, d in open_deleg:
            st.markdown(f'- **{r}** · {d["frm"]} → {d["to_"]} · {d["action"]} · '
                        f'<span class="ri-tag" style="background:#d97706">{d["status"]}</span>',
                        unsafe_allow_html=True)
    else:
        st.caption("No open delegations.")


# ================================================================= Analytics / Settings placeholders
def render_placeholder(name, note):
    st.subheader(name)
    st.info(f'**Placeholder — not yet implemented.** {note}')


# ================================================================= dispatch
if nav == "Overview":
    render_overview()
elif nav == journey.WORKSPACE_NAV:
    render_incidents(you_role)
elif nav == "Operations":
    render_operations(you_role)
elif nav == "Analytics":
    render_placeholder("Analytics", "Planned: MTTR, SLA/OLA breach trends, repeat-incident and "
                                    "resolution-confidence analytics over governed data.")

st.divider()
st.caption("Sample data · simulated actions · build v41 — proof of concept, not production.")
