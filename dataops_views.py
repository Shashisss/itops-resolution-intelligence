#!/usr/bin/env python3
"""DataOps persona views — pipelines, DQ, freshness, lineage, contracts.
Separate from IT Ops views; shares the evidence / approval / lifecycle patterns."""
import pandas as pd
import streamlit as st
import dataops_engine as DE

PERSONAS = ["Pipeline intelligence", "Data Engineer", "Data Owner", "Platform Engineer", "Data Consumer"]


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
    st.markdown(f'**Lifecycle:** {_stepper(inc["stage"])}')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stage", inc["stage"])
    c2.metric("Pipeline owner", pipe.get("owner_team", inc["owner_team"]))
    c3.metric("Freshness", fresh_txt, delta="SLA breach" if breach else None, delta_color="inverse" if breach else "normal")
    c4.metric("Downstream consumers", len(cons))
    st.markdown(f'**Dataset:** {name} ({data["datasets"][ds]["layer"]})   ·   **Blocker:** {inc["blocker"] or "—"}   ·   '
                f'**Priority:** {inc["priority"]}')
    con = next((c for c in data["contracts"] if c["dataset_id"] == ds), None)
    if con:
        st.markdown(f'**Data contract:** {con["name"]} {con["version"]} · owner {con["owner"]}')
    if breach or _dq(data, ds):
        st.caption("Detection is rule-based (freshness SLA, DQ thresholds, run status) — not autonomous/learned.")


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
    for h in hyps:
        badge = "✅ CONFIRMED" if h["status"] == "confirmed" else "🔶 SUSPECTED"
        st.markdown(f'- {badge} · *{h["type"]}* · confidence **{h["confidence"]}** — {h["text"]}  \n'
                    f'  ↳ **evidence:** {h["evidence"]}')
    top = hyps[0]
    if top["status"] != "confirmed":
        if st.button("Confirm top hypothesis as root cause", key="dop_confirm_" + inc["id"]):
            DE.confirm_cause(inc["id"], top["key"])
            st.session_state["flash"] = "Root cause CONFIRMED and recorded against the pipeline incident."
            st.rerun()
    return hyps


def action_panel(inc, data):
    st.markdown("---")
    st.markdown("#### Repair & verification   ·   🧪 **SIMULATED**")
    st.caption("Simulation only — no real pipelines are touched. Approval is enforced before high-risk actions.")
    hyps = DE.causes(inc, data)
    rec = DE.recommend(inc, hyps, data)
    applied = st.session_state.get(f'dop_applied_{inc["id"]}', False)
    rows = DE.verification(inc, data, applied)
    st.markdown("**Verification — before / after, with the thresholds that were checked**")
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("Recovery is **simulated**. Thresholds checked: freshness SLA, data-quality rules and downstream health.")
    approved = True
    if rec["mode"] in ("Human approval", "Policy controlled"):
        st.warning(f'🔴 **{rec["mode"]} required** — {rec["action"]}')
        approved = st.checkbox("I approve this action (required before execution)", key="dop_appr_" + inc["id"])
    else:
        st.info(f'🟢 **{rec["mode"]}** — {rec["action"]}')
    if st.button("Apply recommended repair (simulated)", disabled=not approved, type="primary",
                 key="dop_apply_" + inc["id"]):
        st.session_state[f'dop_applied_{inc["id"]}'] = True
        DE.set_stage(inc["id"], "Validated")
        st.session_state["flash"] = ("Simulated repair applied → pipeline validated → downstream healthy. "
                                     "Evidence captured for learning.")
        st.rerun()


# ---------------------------------------------------------------- personas
def pipeline_view(inc, data):
    services = None
    st.subheader("Pipeline intelligence — full walkthrough")
    context_header(inc, data)
    handoff("to the Data Engineer (fix), Platform Engineer (scale/backfill) and Data Owner (impact); "
            "context, contract and blocker carry across.")
    st.subheader("1 · The pipeline story")
    for p in DE.lineage_paths(inc["dataset_id"], data["G"]):
        st.write("→ " + " → ".join(data["datasets"][n]["name"] for n in p))
    st.info(inc["summary"])
    st.subheader("2 · Failure impact (over the lineage graph)")
    downs, cons = DE.impact(inc["dataset_id"], data)
    st.write("**Downstream datasets:** " + (", ".join(data["datasets"][d]["name"] for d in downs) or "—"))
    st.write("**Consumers impacted:** " + (", ".join(cons) or "—"))
    st.subheader("3 · Root cause — hypotheses with evidence")
    hypotheses(inc, data)
    st.subheader("4 · Recommended repair (policy-governed)")
    rec = DE.recommend(inc, DE.causes(inc, data), data)
    st.write(f'**Recommended:** {rec["action"]}  ·  Risk: **{rec["risk"]}**  ·  Gate: **{rec["mode"]}**  ·  '
             f'Operator: **{rec["actor"]}**')
    st.subheader("5 · Analytics")
    a = DE.analytics(inc, data)
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Recovery time", f'{a["recovery_time_min"]} min')
    a2.metric("Freshness lag", f'{a["freshness_lag_min"]} min')
    a3.metric("Data quality", a["quality"])
    a4.metric("Pipeline reliability", f'{a["reliability_pct"]}%')
    action_panel(inc, data)


def data_engineer_view(inc, data):
    st.subheader("Data Engineer — triage & fix")
    context_header(inc, data)
    run = DE.latest_run(inc["pipeline_id"], data["runs"])
    if run:
        st.markdown(f'**Latest run:** {run["id"]} · **{run["status"]}** · {run["started_at"]} · '
                    f'{run["duration_min"]} min' + (f' · `{run["error"]}`' if run["error"] else ''))
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
    st.dataframe(pd.DataFrame(rows), hide_index=True)
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
    st.dataframe(pd.DataFrame([{"run": r["id"], "status": r["status"], "duration_min": r["duration_min"],
                                "rows": r["rows"]} for r in runs]), hide_index=True)
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
