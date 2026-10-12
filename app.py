#!/usr/bin/env python3
"""ITOps Resolution Intelligence — Streamlit POC.
One governed operational record, shaped per persona.
Deterministic graph + rule-based resolution intelligence (not autonomous RCA).
SAMPLE DATA · SIMULATED INTEGRATIONS & ACTIONS."""
import os
import streamlit as st
import engine as E
import personas


def _needs_seed():
    import sqlite3
    if not os.path.exists("data/ops.db"):
        return True
    try:
        con = sqlite3.connect("data/ops.db")
        for t in ("tickets", "kpis", "incidents"):
            con.execute(f"SELECT 1 FROM {t} LIMIT 1")
        cols = [r[1] for r in con.execute("PRAGMA table_info(incidents)")]
        con.close()
        return not {"stage", "owner_team", "blocker", "confirmed_cause"}.issubset(set(cols))
    except Exception:
        return True


def _reset():
    import importlib
    import seed
    importlib.reload(seed)
    st.session_state.clear()


if _needs_seed():
    import seed  # noqa: F401  (writes data/ops.db + data/history.duckdb)

st.set_page_config(page_title="ITOps Resolution Intelligence — POC", layout="wide")
st.title("IT Operations Resolution & Intelligence")
st.caption("Signal → Context → Reason → Recommend → Verify   ·   one governed record, shaped per persona   ·   build v9")

st.info("🧪 **Demo scenario:** a customer-impacting payment incident (**INC-8841**). "
        "Synthetic sample data; integrations and remediation are **simulated**.")

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

services, edges, incidents, changes, metrics, G = E.load()
tickets = E.load_tickets()
kpis = E.load_kpis()
ctx = dict(services=services, edges=edges, incidents=incidents, changes=changes,
           metrics=metrics, tickets=tickets, kpis=kpis, G=G)

ordered = sorted(incidents, key=lambda i: (i["status"] != "open", i["id"]))
titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in ordered}

persona = st.sidebar.selectbox("Persona", personas.PERSONAS)
sel = st.sidebar.selectbox("Context incident", list(titles), format_func=lambda x: titles[x])
st.sidebar.caption("Switch persona to see each role's day-to-day view of the same incident.")
if st.sidebar.button("↺ Reset demo data", key="reset_side"):
    _reset()
    st.rerun()

inc = next(i for i in incidents if i["id"] == sel)

if persona == "Incident intelligence":
    personas.incident_view(inc, ctx)
elif persona == "CSM":
    personas.csm_view(inc, ctx)
elif persona == "L1 Engineer":
    personas.l1_view(inc, ctx)
elif persona == "L2 / L3 Engineer":
    personas.l2_view(inc, ctx)
elif persona == "Developer":
    personas.developer_view(ctx)
elif persona == "Incident Manager":
    personas.im_view(inc, ctx)
