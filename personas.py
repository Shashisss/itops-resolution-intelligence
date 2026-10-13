#!/usr/bin/env python3
"""Persona views — one governed record, shaped per role.
Deterministic graph + rule-based resolution intelligence (NOT autonomous/learned RCA).
Sample data · simulated integrations and actions."""
import datetime as dt
import duckdb
import pandas as pd
import streamlit as st
import engine as E
import csm
import developer
import journey

SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}
STAGES = ["Detected", "Triaged", "Diagnosed", "Change raised", "Fix in progress", "Fix applied", "Verified", "Closed"]
PERSONAS = ["Incident intelligence", "CSM", "L1 Engineer", "L2 / L3 Engineer", "Developer", "Incident Manager"]
METRIC_LABELS = {"p95_latency_ms": "Latency (p95, ms)", "error_rate_pct": "Error rate (%)",
                 "active_connections": "DB connections", "cpu_pct": "DB CPU (%)"}
SLA_ASSUMPTION = ("Priority-based estimate: clock from incident creation, target hours by priority. "
                  "It does NOT model pause rules, business calendars or actual SLA events.")


# ---------------------------------------------------------------- helpers
def _stepper(stage):
    idx = STAGES.index(stage) if stage in STAGES else 0
    return "   ".join(("✔" if i < idx else "●" if i == idx else "○") + " " + s for i, s in enumerate(STAGES))


def _sla_detail(inc):
    target = SLA_HOURS.get(inc["priority"], 8)
    try:
        elapsed = (dt.datetime.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 3600
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


def _latest_change(inc, ctx):
    return E.latest_change(inc, ctx["G"], ctx["changes"])


def context_header(inc, ctx):
    """Carried context + lifecycle + SLA semantics — shown on every persona."""
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
              else "not mapped")
    st.markdown(f'**Blocker:** {inc["blocker"] or "—"}   ·   **Business service:** '
                f'{services[biz]["name"] if biz else "—"}   ·   **Priority:** {inc["priority"]}')
    tk = next((t for t in ctx["tickets"] if t["incident_id"] == inc["id"]), None)
    if tk:
        st.markdown(f'**Dev ticket:** {tk["id"]} ({tk["status"]}) · {tk["assignee"]}')
    st.caption(f'SLA — {SLA_ASSUMPTION}')
    if not k:
        st.caption("No business KPI is mapped for this scenario — impact shown as service-level only.")
    journey.render_verdict(st.session_state.get(f'verdict_{inc["id"]}', "Investigating"))


def handoff(text):
    st.markdown(f'<div style="background:#EEF2FF;border-left:4px solid #4F46E5;padding:8px 12px;'
                f'border-radius:6px;margin:4px 0 10px 0;font-size:14px">🔁 <b>Handoff</b> — {text}</div>',
                unsafe_allow_html=True)


def _carried(inc, ctx, biz, sla_txt):
    k = _kpi(ctx, biz)
    bits = [f'incident **{inc["id"]}**', f'service **{ctx["services"][inc["service_id"]]["name"]}**',
            f'owner **{inc["owner_team"]}**', f'blocker **{inc["blocker"] or "—"}**', f'SLA **{sla_txt}**']
    if k:
        bits.append(f'business KPI **{k["metric"].replace("_"," ")} {k["current"]:.0f}{k["unit"]}**')
    tk = next((t for t in ctx["tickets"] if t["incident_id"] == inc["id"]), None)
    if tk:
        bits.append(f'ticket **{tk["id"]}**')
    return ", ".join(bits)


def hypotheses(inc, ctx):
    hyps = journey.render_hypotheses(E.causes(inc, ctx["G"], ctx["changes"], ctx["metrics"], ctx["services"]))
    if not hyps:
        return hyps
    top = journey.rank(hyps)[0]
    if top["status"] != "confirmed":
        if st.button("Confirm top hypothesis as root cause", key="confirm_" + inc["id"]):
            E.confirm_cause(inc["id"], top["key"])
            journey.add_event(inc["id"], "itops", "verify", f'root cause confirmed: {top["text"]}')
            st.session_state["flash"] = "Root cause CONFIRMED and recorded against the incident."
            st.rerun()
    return hyps


def _verification(inc, ctx, applied):
    services, changes, metrics, G = ctx["services"], ctx["changes"], ctx["metrics"], ctx["G"]
    scope = E.impacted(G, inc["service_id"])
    breaching = {m["metric"]: m for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]}
    rows = []
    for key in ["p95_latency_ms", "error_rate_pct", "active_connections", "cpu_pct"]:
        if key in breaching:
            m = breaching[key]
            rows.append({"check": METRIC_LABELS.get(key, key), "before": f'{m["value"]:.1f}',
                         "threshold checked": f'< {m["threshold"]:.0f}',
                         "after (simulated)": f'{min(m["threshold"]*0.9, m["value"]):.1f}' if applied else "—",
                         "result": "✅ pass" if applied else "⏳ pending"})
    biz = E.business_service(G, E.dependency_paths(G, inc["service_id"])[0], services)
    k = _kpi(ctx, biz)
    if k:
        rows.append({"check": f'Business KPI — {k["metric"].replace("_"," ")}',
                     "before": f'{k["current"]:.1f}{k["unit"]}', "threshold checked": f'≥ {k["baseline"]:.1f}{k["unit"]}',
                     "after (simulated)": f'{k["baseline"]:.1f}{k["unit"]}' if applied else "—",
                     "result": "✅ pass" if applied else "⏳ pending"})
    return rows, k


def action_panel(inc, ctx):
    st.markdown("---")
    st.markdown("#### Remediation & verification   ·   🧪 **SIMULATED**")
    st.caption("The outcome depends on the action chosen; verification is independent. Approval is enforced for "
               "high-risk actions.")
    labels = [f'{o["id"]} · {o["label"]}' for o in E.IT_REMEDIATION]
    sel = st.radio("Remediation option", labels, key="it_opt_" + inc["id"])
    opt = E.IT_REMEDIATION[labels.index(sel)]
    applied = st.session_state.get(f'it_opt_applied_{inc["id"]}') == opt["id"]
    rows = E.it_verification(inc, ctx, opt, applied)
    journey.render_verification(rows, "SRE verification service")
    journey.render_verdict(journey.verdict(rows, applied))
    st.caption("Recovery is **simulated**; the thresholds checked are shown above (latency, error rate, DB "
               "connections, business KPI).")
    approved = True
    if opt["mode"] in ("Human approval", "Policy controlled"):
        st.warning(f'🔴 **{opt["mode"]} required** — {opt["label"]}')
        approved = st.checkbox("I approve this action (required before execution)", key="it_appr_" + inc["id"])
    else:
        st.info(f'🟢 **{opt["mode"]}** — {opt["label"]}')
    if st.button("Apply selected action (simulated)", disabled=not approved, type="primary",
                 key="it_apply_" + inc["id"]):
        v = journey.verdict(E.it_verification(inc, ctx, opt, True), True)
        st.session_state[f'it_opt_applied_{inc["id"]}'] = opt["id"]
        st.session_state[f'verdict_{inc["id"]}'] = v
        E.set_stage(inc["id"], {"Verified": "Verified", "Mitigated": "Fix applied",
                                "Recovery failed": "Fix in progress"}.get(v, "Fix applied"))
        journey.add_event(inc["id"], "itops", "repair", f'{opt["label"]} — independent verification: {v}')
        st.session_state["flash"] = f'Action applied (simulated). Independent verification → **{v}**.'
        st.rerun()


# ---------------------------------------------------------------- personas
def incident_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("Incident intelligence — full walkthrough")
    context_header(inc, ctx)
    handoff("to L2/L3 (diagnosis), Developer (fix via ticket), and back to the Incident Manager to verify.")
    st.subheader("Detection")
    journey.render_detection(inc["id"], "Monitoring / SRE")
    st.subheader("Operational timeline")
    journey.render_timeline(inc["id"])
    st.subheader("1 · The operational story")
    st.write(" → ".join(services[n]["name"] for n in E.dependency_paths(G, inc["service_id"])[0]))
    st.info(inc["summary"])
    st.subheader("2 · Business impact (computed over the graph)")
    df = _kpi_df()
    st.line_chart(df[df.scenario == "current"].set_index("ts")["value"], height=150)
    st.subheader("3 · Root cause — hypotheses with evidence")
    hypotheses(inc, ctx)
    st.subheader("4 · Recommended action (policy-governed)")
    rec = E.recommend(inc, E.causes(inc, G, changes, metrics, services))
    st.write(f'**Recommended:** {rec["action"]}  ·  Risk: **{rec["risk"]}**  ·  Gate: **{rec["mode"]}**  ·  '
             f'Next actor: **{rec["actor"]}**')
    st.subheader("5 · Related incidents")
    sim = E.similar(incidents, inc)
    if sim:
        st.caption(f'Above the relevance threshold ({E.SIMILARITY_THRESHOLD}); weak matches rejected.')
        for s in sim:
            st.write(f'- {s}')
    else:
        st.caption(f'No related incidents above the relevance threshold ({E.SIMILARITY_THRESHOLD}).')
    st.subheader("6 · Change risk")
    ch = _latest_change(inc, ctx)
    if ch:
        cr = E.change_risk(ch, G, services, incidents)
        st.write(f'**{ch["id"]}** · {ch["description"]}  (deployed {ch["deployed_at"]})  ·  risk **{cr["risk"]}** '
                 f'(gate {cr["gate"]})')
        st.write("Blast radius: " + (", ".join(cr["blast"]) or "—"))
    else:
        st.caption("No recent change in the impacted subgraph.")
    action_panel(inc, ctx)
    applied = bool(st.session_state.get(f'it_opt_applied_{inc["id"]}'))
    journey.render_resolution(inc["id"], applied, _sla_detail(inc)[0], inc["owner_team"])
    journey.render_correlation(inc["id"])


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
    biz = E.business_service(G_ := ctx["G"], E.dependency_paths(ctx["G"], inc["service_id"])[0], services)
    handoff(f'to Incident Manager / L1 — {_carried(inc, ctx, biz, _sla_detail(inc)[0])}.')


def l1_view(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    st.subheader("L1 / Service Desk — triage & first response")
    context_header(inc, ctx)
    biz = E.business_service(G, E.dependency_paths(G, inc["service_id"])[0], services)
    st.markdown(f'**What happened:** {inc["summary"]}')
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    if rec["mode"] in ("Autonomous", "Auto"):
        st.success(f'🟢 **Do this now (allowed):** {rec["action"]}')
    else:
        st.error(f'🔴 **Escalate — requires {rec["mode"]}:** {rec["action"]}')
    st.markdown("**Triage checklist**")
    st.write(f'- Affected service: **{services[inc["service_id"]]["name"]}**')
    st.write(f'- Business impact: {"customer-impacting — see CSM narrative" if biz else "service-level only"}')
    st.write(f'- Next actor: **{rec["actor"]}**')
    sim = E.similar(incidents, inc)
    st.markdown("**Related / known errors**")
    for s in (sim or [f"No related incidents above the relevance threshold ({E.SIMILARITY_THRESHOLD})."]):
        st.write(f'- {s}')
    with st.expander("Runbook steps (L1)"):
        for step in ["Check recent deployments on the affected service",
                     "Verify DB connections / latency metrics",
                     "Apply known remediation if policy allows",
                     "If unresolved in 15 min → escalate to L2 / owning team"]:
            st.write(f'- {step}')
    handoff(f'to L2/L3 — {_carried(inc, ctx, biz, _sla_detail(inc)[0])}.')


def l2_view(inc, ctx):
    st.subheader("L2 / L3 — diagnosis & root cause")
    context_header(inc, ctx)
    hypotheses(inc, ctx)
    services, changes, metrics, G = ctx["services"], ctx["changes"], ctx["metrics"], ctx["G"]
    scope = E.impacted(G, inc["service_id"])
    st.markdown("**Dependency path(s)** — handles multiple parents")
    for p in E.dependency_paths(G, inc["service_id"]):
        st.write("→ " + " → ".join(services[n]["name"] for n in p))
    st.markdown("**Telemetry (breaching)**")
    rows = [{"service": m["service_id"], "metric": m["metric"], "value": m["value"], "threshold": m["threshold"]}
            for m in metrics if m["service_id"] in scope and m["value"] > m["threshold"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    ch = _latest_change(inc, ctx)
    if ch:
        cr = E.change_risk(ch, G, services, ctx["incidents"])
        st.markdown(f'**Suspect change:** {ch["id"]} · {ch["description"]} · risk **{cr["risk"]}** ({cr["gate"]})')
    biz = E.business_service(G, E.dependency_paths(G, inc["service_id"])[0], services)
    handoff(f'to the Developer — {_carried(inc, ctx, biz, _sla_detail(inc)[0])}.')


def developer_view(ctx):
    st.subheader("Developer — Jira ticket context")
    st.caption("The evidence bundle that travels with the work — no context-transfer calls.")
    tmap = {t["id"]: f'{t["id"]} · {t["title"]}' for t in ctx["tickets"]}
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
        st.markdown(f'**Business impact (scenario KPI):** {b.get("metric_name","checkout success")} '
                    f'**{b["kpi"]}%** (baseline {b.get("baseline",98.5)}%)')
    else:
        st.caption("No business KPI mapped for this scenario.")
    st.markdown("**RCA hypotheses:**")
    for cch in (b["causes"] or ["no change or metric breach found"]):
        st.write("- " + cch)
    st.success(f'**What to fix:** {b["fix_hint"]}')
    st.info(f'**Acceptance / definition of done:** {b["acceptance"]}')
    st.markdown(f'**How it is verified:** {b["verify"]}')
    with st.expander("📎 Evidence ledger", expanded=True):
        for e in b["evidence"]:
            st.write("· " + e)
    handoff("back to L2/L3 and the Incident Manager once the fix is ready — context, owner and blocker carry over.")


def im_view(inc, ctx):
    services, changes, metrics, incidents, tickets, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                         ctx["incidents"], ctx["tickets"], ctx["G"])
    st.subheader("Incident Manager — drive resolution")
    context_header(inc, ctx)
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    rel_ticket = next((t for t in tickets if t["incident_id"] == inc["id"]), None)
    ch = _latest_change(inc, ctx)
    sla_txt, rem, target, elapsed = _sla_detail(inc)
    biz = E.business_service(G, E.dependency_paths(G, inc["service_id"])[0], services)

    st.markdown(f'**Why isn’t this moving?** Blocker: **{inc["blocker"] or "—"}**')
    st.markdown(f'**Next actor:** **{rec["actor"]}**  ·  **Action:** {rec["action"]} ({rec["mode"]})')
    st.markdown("**Who is working on it**")
    st.write(f'- Owner team: **{inc["owner_team"]}**')
    if rel_ticket:
        st.write(f'- Dev ticket: **{rel_ticket["id"]}** ({rel_ticket["status"]}) · {rel_ticket["assignee"]}')
    if ch:
        st.write(f'- Change owner: **{ch["owner"]}** ({ch["id"]}, deployed {ch["deployed_at"]})')
    st.markdown("**Escalation signal**")
    if inc["status"] == "open" and rem is not None and rem < target * 0.5:
        st.error(f'🔴 Escalate — {sla_txt}; customer-impacting.')
    else:
        st.success("🟢 On track — no escalation required.")

    st.markdown("#### Hand off a specific action")
    target_who = st.radio("Hand off to", ["L2 / L3 Engineer", "Developer (via ticket)"],
                          key="im_target_" + inc["id"], horizontal=True)
    st.markdown(f'- **Action handed off:** {rec["action"]}')
    st.markdown(f'- **Owner:** {rec["actor"]}   ·   **Blocker:** {inc["blocker"] or "—"}')
    if rel_ticket:
        st.markdown(f'- **Developer ticket:** {rel_ticket["id"]} ({rel_ticket["status"]}) · {rel_ticket["assignee"]}')
    st.markdown(f'- **Carried context:** {_carried(inc, ctx, biz, sla_txt)}')
    if st.button("Record handoff (simulated)", key="handoff_" + inc["id"]):
        st.session_state["flash"] = (f'Handoff recorded → **{target_who}**: “{rec["action"]}” '
                                     f'(owner {rec["actor"]}, blocker {inc["blocker"] or "—"}).')
        st.rerun()

    st.markdown("**Timeline**")
    st.write(f'- Incident raised: {inc["created_at"]}')
    if ch:
        st.write(f'- Suspect change deployed: {ch["deployed_at"]}')
    if rel_ticket:
        st.write(f'- Dev ticket created: {rel_ticket["created_at"]}')
    handoff("to L2/L3 (diagnosis) and the Developer (fix); approve high-risk actions here.")
