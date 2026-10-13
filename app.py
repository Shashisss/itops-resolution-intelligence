#!/usr/bin/env python3
"""Resolution Intelligence — Streamlit POC.
One governed platform across two operational domains, selected at the top:
  • IT Ops   — incidents, changes, services, SLAs, RCA
  • DataOps  — pipeline failures, data quality, freshness, lineage
Deterministic graph + rule-based reasoning. SAMPLE DATA · SIMULATED ACTIONS."""
import os
import streamlit as st
import engine as E
import personas
import dataops_engine as DE
import dataops_views as DV
import liveops_view
import viz


def _needs_seed():
    import sqlite3
    if not os.path.exists("data/ops.db"):
        return True
    try:
        con = sqlite3.connect("data/ops.db")
        required = ("tickets", "kpis", "incidents", "pipelines", "dop_incidents", "timeline",
                    "correlations", "service_data", "live_events", "comments", "delegations", "notifications")
        for t in required:
            con.execute(f"SELECT 1 FROM {t} LIMIT 1")
        con.close()
        return False
    except Exception:
        return True


def _reset():
    import importlib
    import seed
    importlib.reload(seed)
    st.session_state.clear()


if _needs_seed():
    import seed  # noqa: F401  (writes data/ops.db + data/history.duckdb)

st.set_page_config(page_title="Resolution Intelligence — POC", layout="wide")
viz.inject_css()
st.title("Resolution Intelligence")
st.caption("Operational intelligence across IT Ops and DataOps — one governed platform   ·   build v22")

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

# ---- operations-domain switcher (header) ----
st.markdown("**Select your operations domain**")
domain = st.radio("Operations domain", ["IT Ops", "DataOps", "Live Operations"], horizontal=True, index=0,
                  label_visibility="collapsed", key="ops_domain")


# ================================================================= IT Ops
def render_itops():
    services, edges, incidents, changes, metrics, G = E.load()
    ctx = dict(services=services, edges=edges, incidents=incidents, changes=changes, metrics=metrics,
               tickets=E.load_tickets(), kpis=E.load_kpis(), G=G)
    ordered = sorted(incidents, key=lambda i: (i["status"] != "open", i["id"]))
    titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in ordered}
    persona = st.sidebar.selectbox("Persona", personas.PERSONAS, key="it_persona")
    sel = st.sidebar.selectbox("Context incident", list(titles), format_func=lambda x: titles[x], key="it_inc")
    st.sidebar.caption("Switch persona to see each role's day-to-day view of the same incident.")
    if st.sidebar.button("↺ Reset sample data", key="reset_it"):
        _reset(); st.rerun()
    inc = next(i for i in incidents if i["id"] == sel)
    {"Incident intelligence": personas.incident_view, "CSM": personas.csm_view,
     "L1 Engineer": personas.l1_view, "L2 / L3 Engineer": personas.l2_view,
     "Developer": lambda i, c: personas.developer_view(c),
     "Incident Manager": personas.im_view}[persona](inc, ctx)


# ================================================================= DataOps
def render_dataops():
    data = DE.load()
    ordered = sorted(data["incidents"], key=lambda i: (i["status"] != "open", i["id"]))
    titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in ordered}
    persona = st.sidebar.selectbox("Persona", DV.PERSONAS, key="dop_persona")
    sel = st.sidebar.selectbox("Pipeline incident", list(titles), format_func=lambda x: titles[x], key="dop_inc")
    st.sidebar.caption("Pipelines, data quality, freshness and lineage — shaped per role.")
    if st.sidebar.button("↺ Reset sample data", key="reset_dop"):
        _reset(); st.rerun()
    inc = next(i for i in data["incidents"] if i["id"] == sel)
    {"Pipeline intelligence": DV.pipeline_view, "Data Engineer": DV.data_engineer_view,
     "Data Owner": DV.data_owner_view, "Platform Engineer": DV.platform_engineer_view,
     "Data Consumer": DV.data_consumer_view}[persona](inc, data)


def render_liveops():
    role = st.sidebar.selectbox("You are (role)", liveops_view.ROLES, key="lo_role")
    name = st.sidebar.text_input("Your name", value="You", key="lo_name")
    st.sidebar.caption("Post updates, delegate actions and accept assignments — shared across the team.")
    if st.sidebar.button("↺ Reset sample data", key="reset_lo"):
        _reset(); st.rerun()
    liveops_view.render(name, role)


if domain == "IT Ops":
    render_itops()
elif domain == "DataOps":
    render_dataops()
else:
    render_liveops()
