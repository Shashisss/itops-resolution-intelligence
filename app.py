#!/usr/bin/env python3
"""ITOps Resolution Intelligence — Streamlit POC.
One governed operational record, shaped per persona: CSM · L1 · L2/L3 · Developer · Incident Manager."""
import os
import streamlit as st
import engine as E
import personas

# Hosted filesystems are ephemeral: seed sample data on first run (or when schema is outdated).
def _needs_seed():
    import sqlite3
    if not os.path.exists("data/ops.db"):
        return True
    try:
        con = sqlite3.connect("data/ops.db")
        con.execute("SELECT 1 FROM tickets LIMIT 1")
        con.close()
        return False
    except Exception:
        return True


if _needs_seed():
    import seed  # noqa: F401  (writes data/ops.db + data/history.duckdb)

st.set_page_config(page_title="ITOps Resolution Intelligence — POC", layout="wide")
st.title("IT Operations Resolution & Intelligence")
st.caption("Signal → Context → Reason → Recommend → Verify   ·   one governed record, shaped per persona   ·   build v5")

services, edges, incidents, changes, metrics, G = E.load()
tickets = E.load_tickets()
ctx = dict(services=services, edges=edges, incidents=incidents, changes=changes,
           metrics=metrics, tickets=tickets, G=G)

titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in incidents}

# ---- persona + context selectors ----
persona = st.sidebar.selectbox("Persona", personas.PERSONAS)
sel = st.sidebar.selectbox("Context incident", list(titles), format_func=lambda x: titles[x])
st.sidebar.caption("Switch persona to see each role's day-to-day view of the same incident.")
inc = next(i for i in incidents if i["id"] == sel)

# ---- dispatch to the persona view ----
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
