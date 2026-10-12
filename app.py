#!/usr/bin/env python3
"""ITOps Resolution Intelligence — Streamlit POC.
One governed operational record, shaped per persona.
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


if _needs_seed():
    import seed  # noqa: F401  (writes data/ops.db + data/history.duckdb)

st.set_page_config(page_title="ITOps Resolution Intelligence — POC", layout="wide")
st.title("IT Operations Resolution & Intelligence")
st.caption("Signal → Context → Reason → Recommend → Verify   ·   one governed record, shaped per persona   ·   build v7")

# sample-data / simulation banner (P2: clearly label sample data & simulated integrations)
st.info("🧪 **Demo environment** — synthetic **sample data**; integrations and remediation actions are **simulated**. "
        "Nothing here touches real systems.")

# flash message from a previous action
flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

services, edges, incidents, changes, metrics, G = E.load()
tickets = E.load_tickets()
kpis = E.load_kpis()
ctx = dict(services=services, edges=edges, incidents=incidents, changes=changes,
           metrics=metrics, tickets=tickets, kpis=kpis, G=G)

# open incidents first in the selector
ordered = sorted(incidents, key=lambda i: (i["status"] != "open", i["id"]))
titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in ordered}

# ---- first-time guidance (P2) ----
with st.expander("👋 How to use this demo", expanded=not st.session_state.get("seen_intro", False)):
    st.markdown(
        "- **Persona** (sidebar): switch to see each role's day-to-day view of the *same* incident.\n"
        "- **Context incident** (sidebar): pick the incident everything is scoped to.\n"
        "- Follow the **lifecycle** stepper at the top of each view; **handoffs** show what carries to the next role.\n"
        "- In *Incident intelligence*, confirm a **root cause**, then **apply the (simulated) action** — approval is "
        "enforced and the outcome is verified against criteria.\n"
        "- **Reset demo data** (below) restores the sample scenario.")
    st.session_state["seen_intro"] = True

# ---- selectors + demo controls ----
persona = st.sidebar.selectbox("Persona", personas.PERSONAS)
sel = st.sidebar.selectbox("Context incident", list(titles), format_func=lambda x: titles[x])
st.sidebar.caption("Switch persona to see each role's day-to-day view of the same incident.")
if st.sidebar.button("↺ Reset demo data"):
    import importlib
    import seed
    importlib.reload(seed)
    st.session_state.clear()
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
