#!/usr/bin/env python3
"""Resolution Intelligence — Streamlit POC.
One governed platform across IT Ops and DataOps.
Deterministic graph + rule-based reasoning. SAMPLE DATA · SIMULATED ACTIONS."""
import os
import streamlit as st
import engine as E
import personas
import dataops_engine as DE
import dataops_views as DV
import liveops_view
import command_center
import viz

ROLES_UNION = ["CSM", "L1 Engineer", "L2 / L3 Engineer", "Developer", "Incident Manager",
               "Data Engineer", "Data Owner", "Platform Engineer", "Data Consumer"]


def _needs_seed():
    import sqlite3
    if not os.path.exists("data/ops.db"):
        return True
    try:
        con = sqlite3.connect("data/ops.db")
        required = ("tickets", "kpis", "incidents", "pipelines", "dop_incidents", "timeline",
                    "correlations", "service_data", "live_events", "comments", "delegations", "notifications",
                    "olas")
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


def _reset_control(key):
    if st.session_state.get("confirm_reset_" + key):
        st.sidebar.warning("Reset wipes all changes (comments, delegations, stages).")
        a, b = st.sidebar.columns(2)
        if a.button("Confirm", key="rc_yes_" + key):
            _reset(); st.session_state["confirm_reset_" + key] = False; st.rerun()
        if b.button("Cancel", key="rc_no_" + key):
            st.session_state["confirm_reset_" + key] = False; st.rerun()
    else:
        if st.sidebar.button("↺ Reset sample data", key="rc_" + key):
            st.session_state["confirm_reset_" + key] = True; st.rerun()


if _needs_seed():
    import seed  # noqa: F401

st.set_page_config(page_title="Resolution Intelligence — POC", layout="wide")
viz.inject_css()
st.title("Resolution Intelligence")
st.caption("Operational intelligence across IT Ops and DataOps — one governed platform")

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

# ---- one navigation system: domain in the header ----
domain = st.radio("Operations domain", ["IT Ops", "DataOps", "Live Operations"], horizontal=True, index=0,
                  key="ops_domain")

# ---- one identity + one autonomy setting (shared across all domains) ----
viz.brand()
you_role = st.sidebar.selectbox("👤 Signed in as (role)", ROLES_UNION, key="you_role")
st.sidebar.checkbox("🤖 Auto-coordinate on open (autonomous)", key="auto_coord",
                    help="Coordination (assign + notify) is autonomous under policy; production changes "
                         "still require human approval.")
with st.sidebar.expander("🎨 Colour legend"):
    viz.legend()
st.sidebar.divider()


# ================================================================= IT Ops
def render_itops():
    services, edges, incidents, changes, metrics, G = E.load()
    ctx = dict(services=services, edges=edges, incidents=incidents, changes=changes, metrics=metrics,
               tickets=E.load_tickets(), kpis=E.load_kpis(), G=G)
    ordered = sorted(incidents, key=lambda i: (i["status"] != "open", i["id"]))
    titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in ordered}
    view = st.sidebar.radio("View", ["Overview", "Guided journey", "By role"], key="it_view")
    persona = None
    if view == "By role":
        default = you_role if you_role in personas.PERSONAS else personas.PERSONAS[0]
        persona = st.sidebar.selectbox("View as role", personas.PERSONAS,
                                       index=personas.PERSONAS.index(default), key="it_persona")
    sel = st.sidebar.selectbox("Context incident", list(titles), format_func=lambda x: titles[x], key="it_inc")
    _reset_control("it")
    inc = next(i for i in incidents if i["id"] == sel)
    if view == "Overview":
        command_center.it_command(inc, ctx)
    elif view == "Guided journey":
        personas.incident_view(inc, ctx)
    else:
        {"CSM": personas.csm_view, "L1 Engineer": personas.l1_view, "L2 / L3 Engineer": personas.l2_view,
         "Developer": lambda i, c: personas.developer_view(c),
         "Incident Manager": personas.im_view}[persona](inc, ctx)


# ================================================================= DataOps
def render_dataops():
    data = DE.load()
    ordered = sorted(data["incidents"], key=lambda i: (i["status"] != "open", i["id"]))
    titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in ordered}
    view = st.sidebar.radio("View", ["Overview", "Guided journey", "By role"], key="dop_view")
    persona = None
    if view == "By role":
        default = you_role if you_role in DV.PERSONAS else DV.PERSONAS[0]
        persona = st.sidebar.selectbox("View as role", DV.PERSONAS,
                                       index=DV.PERSONAS.index(default), key="dop_persona")
    sel = st.sidebar.selectbox("Pipeline incident", list(titles), format_func=lambda x: titles[x], key="dop_inc")
    _reset_control("dop")
    inc = next(i for i in data["incidents"] if i["id"] == sel)
    if view == "Overview":
        command_center.dop_command(inc, data)
    elif view == "Guided journey":
        DV.pipeline_view(inc, data)
    else:
        {"Data Engineer": DV.data_engineer_view, "Data Owner": DV.data_owner_view,
         "Platform Engineer": DV.platform_engineer_view, "Data Consumer": DV.data_consumer_view}[persona](inc, data)


# ================================================================= Live Operations
def render_liveops():
    name = st.sidebar.text_input("Your name", value="You", key="lo_name")
    _reset_control("lo")
    liveops_view.render(name, you_role)


if domain == "IT Ops":
    render_itops()
elif domain == "DataOps":
    render_dataops()
else:
    render_liveops()

st.divider()
st.caption("Sample data · simulated actions · build v31 — proof of concept, not production.")
