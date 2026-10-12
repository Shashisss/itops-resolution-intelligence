#!/usr/bin/env python3
"""Persona views — each role sees the operational record shaped to their day-to-day work."""
import datetime as dt
import duckdb
import pandas as pd
import streamlit as st
import engine as E
import csm
import developer

SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}
PERSONAS = ["Incident intelligence", "CSM", "L1 Engineer", "L2 / L3 Engineer", "Developer", "Incident Manager"]


def _kpi_df():
    con = duckdb.connect("data/history.duckdb")
    df = con.execute("SELECT ts, value, scenario FROM kpi ORDER BY ts").df()
    con.close()
    return df


def _sla(inc):
    try:
        created = dt.datetime.fromisoformat(inc["created_at"])
        hrs = SLA_HOURS.get(inc["priority"], 8) - (dt.datetime.now() - created).total_seconds() / 3600
        return ("BREACHED" if hrs <= 0 else f"{int(hrs)}h {int((hrs % 1) * 60)}m left"), hrs
    except Exception:
        return "n/a", None


def _head(inc, ctx, sla_txt, biz):
    services = ctx["services"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Incident", inc["id"])
    c2.metric("Priority", inc["priority"])
    c3.metric("SLA", sla_txt)
    c4.metric("Business service", services[biz]["name"] if biz else "—")


# ------------------------------------------------------------------ Incident intelligence (full walkthrough)
def incident_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("Incident intelligence — full walkthrough")
    chain = E.impact_chain(G, inc["service_id"])
    biz = E.business_service(G, chain, services)
    sla_txt, _ = _sla(inc)
    _head(inc, ctx, sla_txt, biz)

    st.subheader("1 · The operational story")
    st.write(" → ".join(services[n]["name"] + f' ({services[n]["type"].replace("_"," ")})'
                       for n in reversed(chain)))
    st.info(inc["summary"])

    st.subheader("2 · Business impact (computed over the graph)")
    df = _kpi_df()
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
    rel = sorted([c for c in changes if c["service_id"] in scope],
                 key=lambda c: c["deployed_at"], reverse=True)
    if rel:
        ch = rel[0]
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


# ------------------------------------------------------------------ CSM
def csm_view(inc, ctx):
    services = ctx["services"]
    st.subheader("Customer Success — customer view")
    st.caption(f"Context: **{inc['id']}** · {services[inc['service_id']]['name']}")
    if st.session_state.get("ctx") != inc["id"]:
        st.session_state["ctx"] = inc["id"]
        st.session_state["q"] = f"What is the status of {services[inc['service_id']]['name']}?"
    sugg = csm.suggestions(inc, services)
    for row in [sugg[i:i + 3] for i in range(0, len(sugg), 3)]:
        cols = st.columns(3)
        for c, s in zip(cols, row):
            if c.button(s, key="csm_" + s):
                st.session_state["q"] = s
                st.rerun()
    q = st.text_input("Ask about this service or incident", key="q")
    if q:
        r = csm.answer(q, persona="CSM")
        st.markdown(r["answer"].replace("\n", "  \n") if r["intent"] == "customer" else r["answer"])
        with st.expander("📎 Evidence ledger", expanded=True):
            for e in r["evidence"]:
                st.write("· " + e)
        if r.get("target"):
            with st.expander("✍️ Draft customer update (validate & edit)", expanded=True):
                st.text_area("Message", value=csm.customer_narrative(r["target"]), height=200, key="narr")


# ------------------------------------------------------------------ L1
def l1_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("L1 / Service Desk — triage & first response")
    chain = E.impact_chain(G, inc["service_id"])
    biz = E.business_service(G, chain, services)
    sla_txt, _ = _sla(inc)
    _head(inc, ctx, sla_txt, biz)
    st.markdown(f'**What happened:** {inc["summary"]}')
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    if rec["mode"] in ("Autonomous", "Auto"):
        st.success(f'🟢 **Do this now (allowed):** {rec["action"]}')
    else:
        st.error(f'🔴 **Escalate — requires {rec["mode"]}:** {rec["action"]}')
    st.markdown("**Triage checklist**")
    st.write(f'- Confirm affected service: **{services[inc["service_id"]]["name"]}**')
    st.write(f'- Business impact: {"customer-impacting — see CSM narrative" if biz else "internal only"}')
    st.write(f'- Next actor: **{rec["actor"]}**')
    st.write("- Check recent deployments / changes below")
    st.markdown("**Known error / similar past incidents**")
    for s in E.similar(incidents, inc):
        st.write(f'- {s}')
    with st.expander("Runbook steps (L1)"):
        for step in ["Check recent deployments on the affected service",
                     "Verify DB connections / latency metrics",
                     "Apply known remediation if policy allows",
                     "If unresolved in 15 min → escalate to L2 / owning team"]:
            st.write(f'- {step}')


# ------------------------------------------------------------------ L2 / L3
def l2_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("L2 / L3 — diagnosis & root cause")
    chain = E.impact_chain(G, inc["service_id"])
    biz = E.business_service(G, chain, services)
    sla_txt, _ = _sla(inc)
    _head(inc, ctx, sla_txt, biz)
    scope = E.impacted(G, inc["service_id"])
    st.markdown("**Dependency path:** " + " → ".join(services[n]["name"] for n in reversed(chain)))
    downstream = sorted(scope - set(chain) - {inc["service_id"]})
    if downstream:
        st.markdown("**Downstream / blast radius:** " + ", ".join(services[n]["name"] for n in downstream))
    st.markdown("**Root-cause evidence (RCA over the graph)**")
    causes = E.causes(inc, G, changes, metrics, services)
    for cch in (causes or [{"text": "no change or metric breach found"}]):
        st.write(f'- {cch["text"]}')
    st.markdown("**Telemetry (breaching)**")
    rows = [{"service": m["service_id"], "metric": m["metric"], "value": m["value"],
             "threshold": m["threshold"]} for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    rel = sorted([c for c in changes if c["service_id"] in scope], key=lambda c: c["deployed_at"], reverse=True)
    if rel:
        ch = rel[0]
        cr = E.change_risk(ch, G, services, incidents)
        st.markdown(f'**Suspect change:** {ch["id"]} · {ch["description"]} · risk **{cr["risk"]}** '
                    f'(gate: {cr["gate"]})')
    rec = E.recommend(inc, causes)
    st.info(f'**Recommended fix:** {rec["action"]}  ·  Mode: {rec["mode"]}  ·  Actor: {rec["actor"]}')
    st.markdown("**Verify after fix:** technical (latency/errors) → service (API) → business (checkout success).")


# ------------------------------------------------------------------ Developer
def developer_view(ctx):
    st.subheader("Developer — Jira ticket context")
    st.caption("The evidence bundle that travels with the work — no context transfer calls.")
    tickets = ctx["tickets"]
    tmap = {t["id"]: f'{t["id"]} · {t["title"]}' for t in tickets}
    tsel = st.selectbox("Jira ticket", list(tmap), format_func=lambda x: tmap[x])
    b = developer.context(tsel)
    if not b:
        st.write("No context found for this ticket.")
        return
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Ticket status", b["ticket"]["status"])
    d2.metric("Assignee", b["ticket"]["assignee"])
    d3.metric("Linked incident", b["incident"]["id"] if b["incident"] else "—")
    d4.metric("SLA", b["sla"])
    if b["incident"]:
        st.markdown(f'**Why this ticket exists:** {b["incident"]["title"]} — {b["incident"]["summary"]}')
    st.markdown(f'**Affected service:** {b["service"]}   ·   **Business service:** {b["business"] or "—"}')
    st.markdown(f'**Dependency path:** {b["path"]}')
    if b["downstream"]:
        st.markdown("**Downstream:** " + ", ".join(b["downstream"]))
    if b["kpi"] is not None:
        st.markdown(f'**Business impact:** checkout success **{b["kpi"]}%** (baseline 98.5%)')
    if b["change"]:
        st.markdown(f'**Suspect change:** {b["change"]["id"]} · {b["change"]["description"]}')
    st.markdown("**RCA hypothesis / evidence:**")
    for cch in (b["causes"] or ["no change or metric breach found"]):
        st.write("- " + cch)
    st.success(f'**What to fix:** {b["fix_hint"]}')
    st.info(f'**Acceptance / definition of done:** {b["acceptance"]}')
    st.markdown(f'**How it is verified:** {b["verify"]}')
    with st.expander("📎 Evidence ledger", expanded=True):
        for e in b["evidence"]:
            st.write("· " + e)


# ------------------------------------------------------------------ Incident Manager
def im_view(inc, ctx):
    services, changes, metrics, incidents, tickets, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                         ctx["incidents"], ctx["tickets"], ctx["G"])
    st.subheader("Incident Manager — drive resolution")
    chain = E.impact_chain(G, inc["service_id"])
    biz = E.business_service(G, chain, services)
    sla_txt, sla_hrs = _sla(inc)
    _head(inc, ctx, sla_txt, biz)
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    rel_ticket = next((t for t in tickets if t["incident_id"] == inc["id"]), None)
    rel_change = next((c for c in changes if c["service_id"] in E.impacted(G, inc["service_id"])), None)
    st.markdown(f'**Why isn’t this moving?** Likely blocker: {causes[0]["text"] if causes else "—"}')
    st.markdown(f'**Next actor:** **{rec["actor"]}**  ·  **Action:** {rec["action"]} ({rec["mode"]})')
    st.markdown("**Who is working on it**")
    st.write(f'- Owner team: **{services[inc["service_id"]]["owner"]}**')
    if rel_ticket:
        st.write(f'- Dev ticket: **{rel_ticket["id"]}** ({rel_ticket["status"]}) · {rel_ticket["assignee"]}')
    if rel_change:
        st.write(f'- Change owner: **{rel_change["owner"]}** ({rel_change["id"]})')
    st.markdown("**Escalation signal**")
    if inc["status"] == "open" and sla_hrs is not None and sla_hrs < SLA_HOURS.get(inc["priority"], 8) * 0.5:
        st.error(f'🔴 Escalate — SLA {sla_txt}; customer-impacting.')
    else:
        st.success("🟢 On track — no escalation required.")
    if biz:
        df = _kpi_df()
        cur = df[df.scenario == "current"]
        st.markdown(f'**Business impact:** {services[biz]["name"]} — checkout success {cur["value"].iloc[-1]:.1f}% '
                    f'(baseline 98.5%).')
    st.markdown("**Timeline**")
    st.write(f'- Incident raised: {inc["created_at"]}')
    if rel_change:
        st.write(f'- Suspect change deployed: {rel_change["deployed_at"]}')
    if rel_ticket:
        st.write(f'- Dev ticket created: {rel_ticket["created_at"]}')
