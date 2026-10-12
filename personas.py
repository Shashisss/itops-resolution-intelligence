#!/usr/bin/env python3
"""Persona views — one governed record, shaped per role.
Sample data · simulated integrations and actions."""
import datetime as dt
import duckdb
import pandas as pd
import streamlit as st
import engine as E
import csm
import developer

SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}
STAGES = ["Detected", "Triaged", "Diagnosed", "Change raised", "Fix in progress", "Fix applied", "Verified", "Closed"]
PERSONAS = ["Incident intelligence", "CSM", "L1 Engineer", "L2 / L3 Engineer", "Developer", "Incident Manager"]


# ---------------------------------------------------------------- helpers
def _stepper(stage):
    idx = STAGES.index(stage) if stage in STAGES else 0
    return "   ".join(("✔" if i < idx else "●" if i == idx else "○") + " " + s for i, s in enumerate(STAGES))


def _sla_detail(inc):
    target = SLA_HOURS.get(inc["priority"], 8)
    try:
        created = dt.datetime.fromisoformat(inc["created_at"])
        elapsed = (dt.datetime.now() - created).total_seconds() / 3600
    except Exception:
        elapsed = 0.0
    rem = target - elapsed
    txt = "BREACHED" if rem <= 0 else f"{int(rem)}h {int((rem % 1) * 60)}m left"
    return txt, rem, target, elapsed


def _kpi(ctx, biz):
    return next((k for k in ctx["kpis"] if k["business_service"] == biz), None) if biz else None


def _kpi_df():
    con = duckdb.connect("data/history.duckdb")
    df = con.execute("SELECT ts, value, scenario FROM kpi ORDER BY ts").df()
    con.close()
    return df


def context_header(inc, ctx):
    """Carried context + lifecycle — shown on every persona."""
    services, G = ctx["services"], ctx["G"]
    chain = E.dependency_paths(G, inc["service_id"])[0]
    biz = E.business_service(G, chain, services)
    sla_txt, rem, target, elapsed = _sla_detail(inc)
    st.markdown(f'**Lifecycle:** {_stepper(inc["stage"])}')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stage", inc["stage"])
    c2.metric("Owner", inc["owner_team"])
    c3.metric("SLA", sla_txt)
    k = _kpi(ctx, biz)
    c4.metric("Business KPI", f'{k["metric"].replace("_"," ")} {k["current"]:.0f}{k["unit"]}' if k
              else (services[biz]["name"] if biz else "—"))
    line = (f'**Blocker:** {inc["blocker"] or "—"}   ·   **Business service:** '
            f'{services[biz]["name"] if biz else "—"}   ·   **Priority:** {inc["priority"]}')
    st.markdown(line)
    tk = next((t for t in ctx["tickets"] if t["incident_id"] == inc["id"]), None)
    if tk:
        st.markdown(f'**Dev ticket:** {tk["id"]} ({tk["status"]}) · {tk["assignee"]}')
    st.caption(f'SLA assumption: clock from incident creation ({inc["created_at"]}); target {target}h for '
               f'{inc["priority"]}; no business-hours pause modelled.')


def handoff(text):
    st.markdown(f'<div style="background:#EEF2FF;border-left:4px solid #4F46E5;padding:8px 12px;'
                f'border-radius:6px;margin:4px 0 10px 0;font-size:14px">🔁 <b>Handoff</b> — {text}</div>',
                unsafe_allow_html=True)


def hypotheses(inc, ctx):
    services, changes, metrics, G = ctx["services"], ctx["changes"], ctx["metrics"], ctx["G"]
    hyps = E.causes(inc, G, changes, metrics, services)
    st.markdown("**RCA hypotheses — suspected vs confirmed (with evidence & confidence)**")
    if not hyps:
        st.info("No change or metric breach is linked to this incident yet.")
        return hyps
    for h in hyps:
        badge = "✅ CONFIRMED" if h["status"] == "confirmed" else "🔶 SUSPECTED"
        st.markdown(f'- {badge} · *{h["type"]}* · confidence **{h["confidence"]}** — {h["text"]}  \n'
                    f'  ↳ **evidence:** {h["evidence"]}')
    top = hyps[0]
    if top["status"] != "confirmed":
        if st.button(f'Confirm top hypothesis as root cause', key="confirm_" + inc["id"]):
            E.confirm_cause(inc["id"], top["key"])
            st.session_state["flash"] = "Root cause CONFIRMED and recorded against the incident."
            st.rerun()
    return hyps


def action_panel(inc, ctx):
    services, changes, metrics, G = ctx["services"], ctx["changes"], ctx["metrics"], ctx["G"]
    st.markdown("---")
    st.markdown("#### Remediation & verification   ·   🧪 **SIMULATED**")
    st.caption("Simulation only — no real systems are touched. Approval is enforced before high-risk actions.")
    hyps = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, hyps)
    scope = E.impacted(G, inc["service_id"])
    breaching = [m for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]]
    biz = E.business_service(G, E.dependency_paths(G, inc["service_id"])[0], services)
    k = _kpi(ctx, biz)
    applied = st.session_state.get(f'applied_{inc["id"]}', False)

    st.markdown("**Verification criteria (must pass to close)**")
    crits = [f'{m["service_id"]} {m["metric"]} back under {m["threshold"]:.0f}' for m in breaching]
    if k:
        crits.append(f'{k["metric"].replace("_"," ")} back to {k["baseline"]:.1f}{k["unit"]}')
    for ccrit in (crits or ["No breaching metrics."]):
        st.write(f'- {ccrit}')

    rows = []
    for m in breaching:
        after = f'{min(m["threshold"]*0.9, m["value"]):.0f}' if applied else "—"
        rows.append({"metric": f'{m["service_id"]} {m["metric"]}', "before": f'{m["value"]:.0f}',
                     "target": f'< {m["threshold"]:.0f}', "after": after})
    if k:
        rows.append({"metric": k["metric"].replace("_", " "), "before": f'{k["current"]:.1f}{k["unit"]}',
                     "target": f'≥ {k["baseline"]:.1f}{k["unit"]}',
                     "after": f'{k["baseline"]:.1f}{k["unit"]}' if applied else "—"})
    st.markdown("**Before / after (simulated)**")
    st.dataframe(pd.DataFrame(rows), hide_index=True)

    approved = True
    if rec["mode"] in ("Human approval", "Policy controlled"):
        st.warning(f'🔴 **{rec["mode"]} required** — {rec["action"]}')
        approved = st.checkbox("I approve this action (required before execution)", key="appr_" + inc["id"])
    else:
        st.info(f'🟢 **{rec["mode"]}** — {rec["action"]}')
    if st.button("Apply recommended action (simulated)", disabled=not approved, type="primary",
                 key="apply_" + inc["id"]):
        st.session_state[f'applied_{inc["id"]}'] = True
        E.set_stage(inc["id"], "Verified")
        st.session_state["flash"] = "Simulated remediation applied → outcome verified → incident advanced to 'Verified'."
        st.rerun()


# ---------------------------------------------------------------- personas
def incident_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("Incident intelligence — full walkthrough")
    context_header(inc, ctx)
    handoff("to L2/L3 for diagnosis, Developer for the fix, and back to the Incident Manager to verify.")
    paths = E.dependency_paths(G, inc["service_id"])
    st.subheader("1 · The operational story")
    st.write(" → ".join(services[n]["name"] for n in paths[0]))
    st.info(inc["summary"])

    st.subheader("2 · Business impact (computed over the graph)")
    df = _kpi_df()
    cur = df[df.scenario == "current"]
    st.line_chart(cur.set_index("ts")["value"], height=150)

    st.subheader("3 · Root cause — hypotheses with evidence")
    hypotheses(inc, ctx)

    st.subheader("4 · Recommended action (policy-governed)")
    rec = E.recommend(inc, E.causes(inc, G, changes, metrics, services))
    st.write(f'**Recommended:** {rec["action"]}')
    st.write(f'Risk: **{rec["risk"]}**  ·  Gate: **{rec["mode"]}**  ·  Next actor: **{rec["actor"]}**')

    st.subheader("5 · Related incidents")
    sim = E.similar(incidents, inc)
    if sim:
        for s in sim:
            st.write(f'- {s}')
    else:
        st.caption("No related incidents above the similarity threshold (0.12).")

    st.subheader("6 · Change risk")
    scope = E.impacted(G, inc["service_id"])
    rel = sorted([c for c in changes if c["service_id"] in scope], key=lambda c: c["deployed_at"], reverse=True)
    if rel:
        ch = rel[0]
        cr = E.change_risk(ch, G, services, incidents)
        st.write(f'**{ch["id"]}** · {ch["description"]}  ·  risk **{cr["risk"]}** (gate {cr["gate"]})')
        st.write("Blast radius: " + (", ".join(cr["blast"]) or "—"))
    else:
        st.caption("No recent change in the impacted subgraph.")

    action_panel(inc, ctx)


def csm_view(inc, ctx):
    services = ctx["services"]
    st.subheader("Customer Success — customer view")
    context_header(inc, ctx)
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
    handoff("to the Incident Manager (status/impact) and L1 (first response) — customer impact, blocker "
            "and owner travel with the incident.")


def l1_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("L1 / Service Desk — triage & first response")
    context_header(inc, ctx)
    chain = E.dependency_paths(G, inc["service_id"])[0]
    biz = E.business_service(G, chain, services)
    st.markdown(f'**What happened:** {inc["summary"]}')
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    if rec["mode"] in ("Autonomous", "Auto"):
        st.success(f'🟢 **Do this now (allowed):** {rec["action"]}')
    else:
        st.error(f'🔴 **Escalate — requires {rec["mode"]}:** {rec["action"]}')
    st.markdown("**Triage checklist**")
    st.write(f'- Affected service: **{services[inc["service_id"]]["name"]}**')
    st.write(f'- Business impact: {"customer-impacting — see CSM narrative" if biz else "internal only"}')
    st.write(f'- Next actor: **{rec["actor"]}**')
    st.markdown("**Related / known errors**")
    sim = E.similar(incidents, inc)
    for s in (sim or ["No related incidents above threshold."]):
        st.write(f'- {s}')
    with st.expander("Runbook steps (L1)"):
        for step in ["Check recent deployments on the affected service",
                     "Verify DB connections / latency metrics",
                     "Apply known remediation if policy allows",
                     "If unresolved in 15 min → escalate to L2 / owning team"]:
            st.write(f'- {step}')
    handoff("to L2/L3 with the triage notes, evidence and the failing checks.")


def l2_view(inc, ctx):
    st.subheader("L2 / L3 — diagnosis & root cause")
    context_header(inc, ctx)
    hypotheses(inc, ctx)
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    scope = E.impacted(G, inc["service_id"])
    paths = E.dependency_paths(G, inc["service_id"])
    st.markdown("**Dependency path(s)** (handles multiple parents)")
    for p in paths:
        st.write("→ " + " → ".join(services[n]["name"] for n in p))
    st.markdown("**Telemetry (breaching)**")
    rows = [{"service": m["service_id"], "metric": m["metric"], "value": m["value"], "threshold": m["threshold"]}
            for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    handoff("to the Developer with the dependency path, breaching metrics and the suspect change.")


def developer_view(ctx):
    st.subheader("Developer — Jira ticket context")
    st.caption("The evidence bundle that travels with the work — no context-transfer calls.")
    tickets = ctx["tickets"]
    tmap = {t["id"]: f'{t["id"]} · {t["title"]}' for t in tickets}
    tsel = st.selectbox("Jira ticket", list(tmap), format_func=lambda x: tmap[x])
    b = developer.context(tsel)
    if not b:
        st.info("No context found for this ticket.")
        return
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Ticket status", b["ticket"]["status"])
    d2.metric("Assignee", b["ticket"]["assignee"])
    d3.metric("Linked incident", b["incident"]["id"] if b["incident"] else "—")
    d4.metric("SLA", b["sla"])
    if b["incident"]:
        st.markdown(f'**Why this ticket exists:** {b["incident"]["title"]} — {b["incident"]["summary"]}')
        st.markdown(f'**Blocker / owner:** {b["incident"].get("blocker") or "—"} · {b["incident"].get("owner_team") or "—"}')
    st.markdown(f'**Affected service:** {b["service"]}   ·   **Business service:** {b["business"] or "—"}')
    st.markdown(f'**Dependency path:** {b["path"]}')
    if b["kpi"] is not None:
        st.markdown(f'**Business impact:** {b.get("metric_name","checkout success")} **{b["kpi"]}%** '
                    f'(baseline {b.get("baseline",98.5)}%)')
    st.markdown("**RCA hypotheses:**")
    for cch in (b["causes"] or ["no change or metric breach found"]):
        st.write("- " + cch)
    st.success(f'**What to fix:** {b["fix_hint"]}')
    st.info(f'**Acceptance / definition of done:** {b["acceptance"]}')
    st.markdown(f'**How it is verified:** {b["verify"]}')
    with st.expander("📎 Evidence ledger", expanded=True):
        for e in b["evidence"]:
            st.write("· " + e)
    handoff("back to L2/L3 and the Incident Manager once the fix is ready — evidence, owner and blocker carry over.")


def im_view(inc, ctx):
    services, changes, metrics, incidents, tickets, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                         ctx["incidents"], ctx["tickets"], ctx["G"])
    st.subheader("Incident Manager — drive resolution")
    context_header(inc, ctx)
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    rel_ticket = next((t for t in tickets if t["incident_id"] == inc["id"]), None)
    rel_change = sorted([c for c in changes if c["service_id"] in E.impacted(G, inc["service_id"])],
                        key=lambda c: c["deployed_at"], reverse=True)[:1]
    sla_txt, rem, target, elapsed = _sla_detail(inc)
    st.markdown(f'**Why isn’t this moving?** Blocker: **{inc["blocker"] or "—"}**')
    st.markdown(f'**Next actor:** **{rec["actor"]}**  ·  **Action:** {rec["action"]} ({rec["mode"]})')
    st.markdown("**Who is working on it**")
    st.write(f'- Owner team: **{inc["owner_team"]}**')
    if rel_ticket:
        st.write(f'- Dev ticket: **{rel_ticket["id"]}** ({rel_ticket["status"]}) · {rel_ticket["assignee"]}')
    if rel_change:
        st.write(f'- Change owner: **{rel_change[0]["owner"]}** ({rel_change[0]["id"]})')
    st.markdown("**Escalation signal**")
    if inc["status"] == "open" and rem is not None and rem < target * 0.5:
        st.error(f'🔴 Escalate — {sla_txt}; customer-impacting.')
    else:
        st.success("🟢 On track — no escalation required.")
    st.markdown("**Timeline**")
    st.write(f'- Incident raised: {inc["created_at"]}')
    if rel_change:
        st.write(f'- Suspect change deployed: {rel_change[0]["deployed_at"]}')
    if rel_ticket:
        st.write(f'- Dev ticket created: {rel_ticket["created_at"]}')
    handoff("to L2/L3 for diagnosis and the Developer for the fix; approve high-risk actions here.")
