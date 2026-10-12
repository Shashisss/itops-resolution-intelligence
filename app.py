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
st.caption("Signal → Context → Reason → Recommend → Verify   ·   one governed record, shaped per persona   ·   build v8")

# first impression: short intro + signposted scenario + visible reset
intro_col, reset_col = st.columns([5, 1])
with intro_col:
    st.markdown("**Start here →** open **Incident intelligence** and walk the sample incident end to end: "
                "customer view → ops → L1 → L2 → Developer → verified resolution.")
with reset_col:
    if st.button("↺ Reset demo", key="reset_top"):
        _reset()
        st.rerun()

st.info("🧪 **Demo scenario:** a customer-impacting payment incident (**INC-8841**). "
        "Synthetic **sample data**; integrations and remediation are **simulated** — nothing touches real systems.")

with st.expander("ℹ️ Scope of this prototype (read first)"):
    st.markdown(
        "- Demonstrates **resolution intelligence** through **deterministic graph traversal + rule-based logic**.\n"
        "- It is **not** autonomous or learned root-cause analysis — hypotheses are *suspected* until a human confirms.\n"
        "- Business KPI and SLA figures are **scenario-specific sample estimates**, not universal metrics.\n"
        "- All remediation and recovery is **simulated**.")

# flash from a previous action
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

with st.expander("👋 How to use this demo", expanded=not st.session_state.get("seen_intro", False)):
    st.markdown(
        "- **Persona** (sidebar): switch to see each role's day-to-day view of the *same* incident.\n"
        "- **Context incident** (sidebar): pick the incident everything is scoped to.\n"
        "- Follow the **lifecycle** stepper; **handoffs** show what carries to the next role.\n"
        "- In *Incident intelligence*: confirm a **root cause**, then **apply the (simulated) action** — "
        "approval is enforced and the outcome is verified against explicit thresholds.\n"
        "- **↺ Reset demo** restores the sample scenario.")
    st.session_state["seen_intro"] = True

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
