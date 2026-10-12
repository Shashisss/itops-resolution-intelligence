#!/usr/bin/env python3
"""ITOps Resolution Intelligence — Streamlit POC.
Tab 1: CSM Assistant — context-aware questions per incident + free-text ask, evidence-led answers.
Tab 2: Incident intelligence — story -> impact -> cause -> recommendation -> change risk -> verify."""
import os
import duckdb
import streamlit as st
import engine as E
import csm

# Hosted filesystems are ephemeral: seed sample data on first run.
if not os.path.exists("data/ops.db"):
    import seed  # noqa: F401  (writes data/ops.db + data/history.duckdb)

st.set_page_config(page_title="ITOps Resolution Intelligence — POC", layout="wide")
st.title("IT Operations Resolution & Intelligence")
st.caption("Signal → Context → Reason → Recommend → Verify   ·   demo on sample data")

services, edges, incidents, changes, metrics, G = E.load()
titles = {i["id"]: f'{i["id"]} · {i["title"]} ({i["status"]})' for i in incidents}

# ---- global context selector (drives both tabs) ----
sel = st.sidebar.selectbox("Context incident", list(titles), format_func=lambda x: titles[x])
st.sidebar.caption("Changing this updates the suggested questions and the incident view.")
inc = next(i for i in incidents if i["id"] == sel)
svc_name = services[inc["service_id"]]["name"]

tab_csm, tab_inc = st.tabs(["💬  CSM Assistant", "🛠  Incident intelligence"])

# ------------------------------------------------------------------ CSM Assistant
with tab_csm:
    st.subheader("CSM Assistant")
    st.caption(f"Context: **{inc['id']}** · {svc_name} — questions update with the incident; ask your own too.")

    # reset the question when the context incident changes
    if st.session_state.get("ctx") != inc["id"]:
        st.session_state["ctx"] = inc["id"]
        st.session_state["q"] = f"What is the status of {svc_name}?"

    sugg = csm.suggestions(inc, services)
    for row in [sugg[i:i + 3] for i in range(0, len(sugg), 3)]:
        cols = st.columns(3)
        for c, s in zip(cols, row):
            if c.button(s, use_container_width=True, key="sg_" + s):
                st.session_state["q"] = s
                st.rerun()

    q = st.text_input("Ask anything about this service or incident", key="q")
    if q:
        r = csm.answer(q)
        if r["intent"] == "customer":
            st.markdown(r["answer"].replace("\n", "  \n"))
        else:
            st.markdown(r["answer"])
        with st.expander("📎 Evidence ledger (citations)", expanded=True):
            for e in r["evidence"]:
                st.write("· " + e)
        with st.expander("✍️ Draft customer update (validate & edit)", expanded=False):
            if r.get("target"):
                st.text_area("Message", value=csm.customer_narrative(r["target"]), height=210, key="narr")
            else:
                st.write("No service identified for a customer update.")

# ------------------------------------------------------------------ Incident intelligence
with tab_inc:
    chain = E.impact_chain(G, inc["service_id"])
    biz = E.business_service(G, chain, services)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Service", services[inc["service_id"]]["name"])
    c2.metric("Priority", inc["priority"])
    c3.metric("Business service", services[biz]["name"] if biz else "—")
    c4.metric("Status", inc["status"])

    st.subheader("1 · The operational story")
    st.write(" → ".join(services[n]["name"] + f' ({services[n]["type"].replace("_"," ")})'
                       for n in reversed(chain)))
    st.info(inc["summary"])

    st.subheader("2 · Business impact (computed over the graph)")
    con = duckdb.connect("data/history.duckdb")
    df = con.execute("SELECT ts, value, scenario FROM kpi ORDER BY ts").df()
    con.close()
    cur = df[df.scenario == "current"]
    st.line_chart(cur.set_index("ts")["value"], height=150)
    if biz:
        st.warning(f'Business KPI at risk: Checkout success ↓ to {cur["value"].iloc[-1]:.1f}% '
                   f'(from ~98.5%) on {services[biz]["name"]}.')

    st.subheader("3 · Likely cause & blockers (RCA over the graph)")
    causes = E.causes(inc, G, changes, metrics, services)
    for cch in (causes or [{"text": "No change or metric breach found in the chain."}]):
        st.write(f'- {cch["text"]}')

    st.subheader("4 · Recommended action (policy-governed)")
    rec = E.recommend(inc, causes)
    st.write(f'**Recommended:** {rec["action"]}')
    mode = {"Autonomous": "🟢 Autonomous", "Auto": "🟠 Auto",
            "Policy controlled": "🟠 Policy controlled", "Human approval": "🔴 Human approval"}
    st.write(f'Risk class: **{rec["risk"]}**  ·  Mode: **{mode.get(rec["mode"], rec["mode"])}**'
             f'  ·  Next actor: **{rec["actor"]}**')

    st.subheader("5 · Similar past incidents (retrieval)")
    for s in E.similar(incidents, inc):
        st.write(f'- {s}')

    st.subheader("6 · Change risk (change intelligence)")
    scope = E.impacted(G, inc["service_id"])
    rel_changes = sorted([c for c in changes if c["service_id"] in scope],
                         key=lambda c: c["deployed_at"], reverse=True)
    if rel_changes:
        ch = rel_changes[0]
        cr = E.change_risk(ch, G, services, incidents)
        st.write(f'**{ch["id"]}** · {ch["description"]}')
        st.write(f'Risk: **{cr["risk"]}**  ·  Gate: **{cr["gate"]}**  ·  '
                 f'Business: {cr["business"] or "—"}  ·  Correlated: {"yes" if cr["correlated"] else "no"}')
        st.write("Blast radius: " + (", ".join(cr["blast"]) or "—"))
        st.write("Why: " + "; ".join(cr["rationale"]))
    else:
        st.write("No recent change in the impacted subgraph.")

    st.subheader("7 · Act & verify")
    approved = True
    if rec["mode"] in ("Human approval", "Policy controlled"):
        approved = st.checkbox("Operator approval required (production / high blast radius)")
    if st.button("Apply recommended action", disabled=not approved, type="primary"):
        st.success("Action executed (simulated): change rolled back, DB connections relaxed.")
        fixed = df[df.scenario == "fixed"]
        st.line_chart(fixed.set_index("ts")["value"], height=150)
        st.success(f'VERIFIED: Checkout success recovered to {fixed["value"].iloc[-1]:.1f}%. '
                   f'Evidence captured → knowledge / policy learning.')
