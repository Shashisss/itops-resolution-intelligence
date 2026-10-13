#!/usr/bin/env python3
"""DataOps persona views — pipelines, DQ, freshness, lineage, contracts.
Separate from IT Ops views; shares the evidence / approval / lifecycle patterns."""
import pandas as pd
import streamlit as st
import dataops_engine as DE
import journey
import viz
import collab

PERSONAS = ["Data Engineer", "Data Owner", "Platform Engineer", "Data Consumer"]


def _stepper(stage):
    idx = DE.STAGES.index(stage) if stage in DE.STAGES else 0
    return "   ".join(("✔" if i < idx else "●" if i == idx else "○") + " " + s for i, s in enumerate(DE.STAGES))


def _fresh(data, ds):
    f = data["fresh"].get(ds)
    if not f:
        return "n/a", False, None, None
    lag = DE._lag_min(f)
    return f'{lag} min (SLA {f["sla_min"]} min)', lag > f["sla_min"], lag, f["sla_min"]


def _dq(data, ds):
    return [d for d in data["dq"] if d["dataset_id"] == ds and d["value"] > d["threshold"]]


def context_header(inc, data):
    ds = inc["dataset_id"]
    pipe = data["pipelines"].get(inc["pipeline_id"], {})
    name = data["datasets"].get(ds, {}).get("name", ds)
    fresh_txt, breach, _, _ = _fresh(data, ds)
    downs, cons = DE.impact(ds, data)
    viz.stepper(DE.STAGES, inc["stage"])
    viz.fact_cards([
        ("Stage", inc["stage"], "#4f46e5"),
        ("Pipeline owner", pipe.get("owner_team", inc["owner_team"]), "#0d9488"),
        ("Freshness", fresh_txt, "#dc2626" if breach else "#16a34a"),
        ("Downstream consumers", str(len(cons)), "#7c3aed"),
    ])
    st.markdown(f'**Dataset:** {name} ({data["datasets"][ds]["layer"]})   ·   **Blocker:** {inc["blocker"] or "—"}   ·   '
                f'**Priority:** {inc["priority"]}')
    con = next((c for c in data["contracts"] if c["dataset_id"] == ds), None)
    if con:
        st.markdown(f'**Data contract:** {con["name"]} {con["version"]} · owner {con["owner"]}')
    if breach or _dq(data, ds):
        st.caption("Detection is rule-based (freshness SLA, DQ thresholds, run status) — not autonomous/learned.")
    journey.render_verdict(st.session_state.get(f'verdict_{inc["id"]}', "Investigating"))


def handoff(text):
    st.markdown(f'<div style="background:#EEF2FF;border-left:4px solid #4F46E5;padding:8px 12px;'
                f'border-radius:6px;margin:4px 0 10px 0;font-size:14px">🔁 <b>Handoff</b> — {text}</div>',
                unsafe_allow_html=True)


def hypotheses(inc, data):
    st.markdown("**Pipeline RCA — hypotheses (suspected vs confirmed, evidence & confidence)**")
    hyps = DE.causes(inc, data)
    if not hyps:
        st.info("No failing run, DQ breach or freshness breach linked yet.")
        return hyps
    hyps = journey.rank(hyps)
    viz.hypothesis_cards(hyps)
    top = hyps[0]
    if top["status"] != "confirmed":
        if st.button("Confirm top hypothesis as root cause", key="dop_confirm_" + inc["id"], type="primary"):
            DE.confirm_cause(inc["id"], top["key"])
            st.session_state["flash"] = "Root cause CONFIRMED and recorded against the pipeline incident."
            st.rerun()
    return hyps


def action_panel(inc, data):
    st.markdown("#### Act — repair   ·   🧪 **SIMULATED**")
    st.markdown('<span class="ri-tag" style="background:#dc2626">🔴 Execution — human approval</span> '
                '<span style="color:#64748b;font-size:12px">(this changes production, so it is risk-gated)</span>',
                unsafe_allow_html=True)
    st.caption("The outcome depends on the action chosen; verification is independent. Approval is enforced for "
               "high-risk actions.")
    labels = [f'{o["id"]} · {o["label"]}' for o in DE.DOP_REMEDIATION]
    sel = st.radio("Repair option", labels, key="dop_opt_" + inc["id"])
    opt = DE.DOP_REMEDIATION[labels.index(sel)]
    approved = True
    if opt["mode"] in ("Human approval", "Policy controlled"):
        st.warning(f'🔴 **{opt["mode"]} required** — {opt["label"]}')
        approved = st.checkbox("I approve this action (required before execution)", key="dop_appr_" + inc["id"])
    else:
        st.info(f'🟢 **{opt["mode"]}** — {opt["label"]}')
    if st.button("Apply selected repair (simulated)", disabled=not approved,
                 type=("primary" if collab.delegations(inc["id"]) else "secondary"),
                 key="dop_apply_" + inc["id"]):
        v = journey.verdict(DE.verification(inc, data, opt, True), True)
        st.session_state[f'dop_opt_applied_{inc["id"]}'] = opt["id"]
        st.session_state[f'verdict_{inc["id"]}'] = v
        DE.set_stage(inc["id"], {"Verified": "Validated", "Mitigated": "Fix applied",
                                 "Recovery failed": "Diagnosed"}.get(v, "Fix applied"))
        journey.add_event(inc["id"], "dataops", "repair", f'{opt["label"]} — independent verification: {v}')
        st.session_state["flash"] = f'Repair applied (simulated). Independent verification → **{v}**.'
        st.rerun()


def verify_panel(inc, data):
    st.markdown("#### Verify — independent verification")
    labels = [f'{o["id"]} · {o["label"]}' for o in DE.DOP_REMEDIATION]
    sel = st.session_state.get("dop_opt_" + inc["id"], labels[0])
    opt = DE.DOP_REMEDIATION[labels.index(sel)] if sel in labels else DE.DOP_REMEDIATION[0]
    applied = st.session_state.get(f'dop_opt_applied_{inc["id"]}') == opt["id"]
    rows = DE.verification(inc, data, opt, applied)
    journey.render_verification(rows, "Data-quality verification service")
    journey.render_verdict(journey.verdict(rows, applied))
    st.caption("Recovery is **simulated**; thresholds checked are shown above (freshness SLA, DQ rules, "
               "downstream health).")
    a = DE.analytics(inc, data)
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Recovery time", f'{a["recovery_time_min"]} min')
    a2.metric("Freshness lag", f'{a["freshness_lag_min"]} min')
    a3.metric("Data quality", a["quality"])
    a4.metric("Pipeline reliability", f'{a["reliability_pct"]}%')
    applied_any = bool(st.session_state.get(f'dop_opt_applied_{inc["id"]}'))
    fresh_txt, _, _, _ = _fresh(data, inc["dataset_id"])
    journey.render_resolution(inc["id"], applied_any, f'freshness {fresh_txt}', inc["owner_team"])
    if applied_any:
        journey.render_recovery_update(
            "Data Owner update",
            f'payments_gold refreshed — freshness within SLA and downstream consumers healthy. '
            f'Independent verification: **{st.session_state.get(f"verdict_{inc["id"]}", "")}**. (Simulated.)')
    journey.render_correlation(inc["id"])


# ---------------------------------------------------------------- personas
def pipeline_view(inc, data):
    st.subheader("Pipeline intelligence — full walkthrough")
    context_header(inc, data)
    fresh_txt0, _, _, _ = _fresh(data, inc["dataset_id"])
    viz.status_bar(f'🔎 {inc["id"]} · {inc["priority"]} · owner {inc["owner_team"]} · '
                   f'freshness {fresh_txt0} · {st.session_state.get(f"verdict_{inc["id"]}", "Investigating")}')

    def detect():
        st.subheader("Detection")
        journey.render_detection(inc["id"], "Data observability")
        st.subheader("Operational timeline")
        journey.render_timeline(inc["id"])
        st.subheader("The pipeline story (lineage)")
        labels = {d: data["datasets"][d]["name"] for d in data["datasets"]}
        stale = tuple(d for d in data["datasets"] if _fresh(data, d)[1])
        viz.chain(DE.lineage_paths(inc["dataset_id"], data["G"])[0], labels,
                  stale=stale, highlight=(inc["dataset_id"],))
        st.info(inc["summary"])
        st.subheader("Failure impact")
        downs, cons = DE.impact(inc["dataset_id"], data)
        st.write("**Downstream datasets:** " + (", ".join(data["datasets"][d]["name"] for d in downs) or "—"))
        st.write("**Consumers impacted:** " + (", ".join(cons) or "—"))

    def diagnose():
        st.subheader("Pipeline RCA — hypotheses")
        hypotheses(inc, data)

    def decide():
        st.subheader("Recommended repair (policy-governed)")
        rec = DE.recommend(inc, DE.causes(inc, data), data)
        viz.rec_card(rec["action"], rec["risk"], rec["mode"], journey.actors(rec))
        journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
        handoff("to the Data Engineer (fix), Platform Engineer (scale/backfill) and Data Owner (impact).")

    journey.wizard("dop_step_" + inc["id"], viz.RESOLUTION_FLOW,
                   {"Detect": detect, "Diagnose": diagnose, "Decide": decide,
                    "Act": lambda: action_panel(inc, data), "Verify": lambda: verify_panel(inc, data)},
                   default=0)


def data_engineer_view(inc, data):
    st.subheader("Data Engineer — triage & fix")
    context_header(inc, data)
    run = DE.latest_run(inc["pipeline_id"], data["runs"])
    if run:
        st.markdown(f'**Latest run:** {run["id"]} · **{run["status"]}** · {run["started_at"]} · '
                    f'{run["duration_min"]} min' + (f' · `{run["error"]}`' if run["error"] else ''))
    rec = DE.recommend(inc, DE.causes(inc, data), data)
    st.info(f'**Diagnostic recommendation:** {rec["action"]}  ·  Gate: **{rec["mode"]}**  ·  Owner: **{rec["actor"]}**')
    hypotheses(inc, data)
    action_panel(inc, data)
    handoff("to the Platform Engineer if capacity/backfill is needed, then the Data Owner to confirm impact.")


def data_owner_view(inc, data):
    st.subheader("Data Owner — impact, freshness & SLA")
    context_header(inc, data)
    downs, cons = DE.impact(inc["dataset_id"], data)
    st.markdown("**Consumers impacted**")
    for c in (cons or ["—"]):
        st.write(f'- {c}')
    st.markdown("**SLA / freshness**")
    rows = []
    ds = inc["dataset_id"]
    fresh_txt, breach, lag, sla = _fresh(data, ds)
    rows.append({"dataset": data["datasets"][ds]["name"], "freshness": fresh_txt,
                 "status": "🔴 breach" if breach else "🟢 ok"})
    for d in downs:
        ft, br, _, _ = _fresh(data, d)
        rows.append({"dataset": data["datasets"][d]["name"], "freshness": ft, "status": "🔴 breach" if br else "🟢 ok"})
    viz.card_rows(rows, "#0d9488")
    if st.session_state.get(f'dop_opt_applied_{inc["id"]}'):
        v = st.session_state.get(f'verdict_{inc["id"]}', "")
        journey.render_recovery_update(
            "Data Owner update",
            f'payments_gold refreshed — freshness back within SLA; downstream consumers '
            f'(Payment service (checkout-api), Finance close) healthy. Independent verification: **{v}**. '
            f'(Simulated.)')
    handoff("to the Data Consumer with a status/ETA once the repair is validated.")


def platform_engineer_view(inc, data):
    st.subheader("Platform Engineer — reliability & capacity")
    context_header(inc, data)
    a = DE.analytics(inc, data)
    c1, c2, c3 = st.columns(3)
    c1.metric("Pipeline reliability", f'{a["reliability_pct"]}%')
    c2.metric("Freshness lag", f'{a["freshness_lag_min"]} min')
    c3.metric("Downstream at risk", a["downstream"])
    runs = [r for r in data["runs"] if r["pipeline_id"] == inc["pipeline_id"]]
    viz.card_rows([{"run": r["id"], "status": r["status"], "duration": f'{r["duration_min"]} min',
                    "rows": r["rows"]} for r in runs], "#475569")
    rec = DE.recommend(inc, DE.causes(inc, data), data)
    st.info(f'Capacity action: {rec["action"]}  ·  Gate: {rec["mode"]}')
    handoff("to the Data Engineer to action the fix; backfill/scale executed here.")


def data_consumer_view(inc, data):
    st.subheader("Data Consumer — can I trust this data?")
    context_header(inc, data)
    ds = inc["dataset_id"]
    fresh_txt, breach, lag, sla = _fresh(data, ds)
    dq = _dq(data, ds)
    st.markdown(f'**{data["datasets"][ds]["name"]} status:** '
                f'{"⚠️ not fresh / not trusted yet" if (breach or dq) else "healthy"}')
    st.markdown(f'- Freshness: {fresh_txt}' + ("  (SLA breached)" if breach else ""))
    if dq:
        for d in dq:
            st.markdown(f'- Data quality: `{d["rule"]}` = {d["value"]:.1f} (limit {d["threshold"]:.1f}) — **failed**')
    else:
        st.markdown("- Data quality: passing")
    st.markdown("**What this means for you:** " + ("downstream reports and features may be stale or incomplete "
                "until the pipeline is repaired and validated." if (breach or dq) else "no impact expected."))
    handoff("the Data Owner will confirm once freshness and quality are restored.")
