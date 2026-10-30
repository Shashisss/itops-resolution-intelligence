#!/usr/bin/env python3
"""DataOps persona views — pipelines, DQ, freshness, lineage, contracts.
Separate from IT Ops views; shares the evidence / approval / lifecycle patterns."""
import datetime as dt
import pandas as pd
import streamlit as st
import dataops_engine as DE
import engine as E
import journey
import runclock
import sections
import shell
import viz
import collab
import graph_views

PERSONAS = ["Data Engineer", "Data Owner", "Platform Engineer", "Data Consumer"]
DOP_STEP_HELP = {
    "Detect": "What failed and when — the failing pipeline run, freshness / DQ alerts, and the lineage of affected datasets.",
    "Triage": "Severity, owner and routing — which data product is affected, the freshness / OLA at risk, and the next engineer.",
    "Investigate": "The evidence: failing run, lineage, DQ breaches and downstream consumers, assembled without a context call.",
    "Correlate": "Ranked pipeline root-cause hypotheses (schema drift, data quality, backlog) with evidence and confidence.",
    "Act": "The recommended repair and next responsible engineer, then the repair itself — production data changes require approval.",
    "Verify": "An independent re-check of freshness, DQ and downstream health → Verified / Mitigated / Recovery failed.",
    "Close": "Closure record — only when independent verification passed.",
    "Learn": "Capture the confirmed cause, the steps that actually worked and the evidence — then match it to past incidents with the same signature.",
}
DOP_HANDOFFS = {
    "Detect": "Data observability → Data Engineer  (failing run + freshness/DQ alerts detected)  ·  OLA 5m",
    "Triage": "Data Engineer → Data Owner  (classified, owned and routed)  ·  OLA 10m",
    "Investigate": "Data Engineer  (run, lineage, DQ and consumers assembled)  ·  OLA 20m",
    "Correlate": "Data Engineer → Data Owner  (root-cause context shared)  ·  OLA 15m",
    "Act": "Data Owner → Data Engineer / Platform Engineer  (execution under the approval gate)  ·  OLA 30m",
    "Verify": "Verification service → Data Owner sign-off → Data Consumer update  ·  OLA 15m",
    "Close": "Data Owner → Data Consumer  (verified closure)",
    "Learn": "Data Owner → Data Platform  (learn record saved and reusable)  ·  OLA 60m",
}


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
    viz.phase_stepper(journey.lifecycle_stage(inc))
    _owner = pipe.get("owner_team", inc["owner_team"])
    ola = next((o for o in E.load_olas() if o["team"] == _owner), None)
    ola_txt = "not defined"
    if ola:
        el = (runclock.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 60
        rem = ola["restore_min"] - el
        ola_txt = f'{ola["restore_min"]}m · ' + ("BREACHED" if rem <= 0 else f'{int(rem)}m left')
    # v103: the owner/wait/SLA facts belong to the hero strip only. One small line for what the
    # hero does not carry — the internal OLA, the blocker and the dataset.
    _blk = (inc["blocker"] or "—").rstrip(".")
    st.caption(f'{_blk[:52]}{"…" if len(_blk) > 52 else ""} · {name} · OLA {ola_txt}')
    if cons:
        st.caption(f'Downstream consumers: {len(cons)}')
    # v103: verdict lives in the identity bar and the rail, not a third time under the stepper.


def handoff(text):
    st.markdown(f'<div style="background:#EEF2FF;border-left:4px solid #4F46E5;padding:8px 12px;'
                f'border-radius:6px;margin:4px 0 10px 0;font-size:14px">🔁 <b>Handoff</b> — {text}</div>',
                unsafe_allow_html=True)


def hypotheses(inc, data, limit=2):
    st.markdown("**Pipeline RCA — hypotheses (suspected vs confirmed, evidence & confidence)**")
    hyps = DE.causes(inc, data)
    if not hyps:
        st.info("No failing run, DQ breach or freshness breach linked yet.")
        return hyps
    hyps = journey.rank(hyps)
    total = len(hyps)
    viz.hypothesis_cards(hyps[:limit] if limit else hyps, total=total, offset=0)
    if limit and len(hyps) > limit:
        with st.expander(f"Show all {len(hyps)} hypotheses"):
            viz.hypothesis_cards(hyps[limit:], total=total, offset=limit)
    top = hyps[0]
    if top["status"] != "confirmed":
        c1, c2 = st.columns([1, 1])
        if c1.button("Confirm top hypothesis as root cause", key="dop_confirm_" + inc["id"], type="primary"):
            DE.confirm_cause(inc["id"], top["key"])
            journey.add_event(inc["id"], "dataops", "verify", f'root cause confirmed: {top["text"]}')
            st.session_state["flash"] = "Root cause CONFIRMED and recorded against the pipeline incident."
            st.rerun()
        if c2.button("Reject hypothesis", key="dop_reject_" + inc["id"]):
            journey.add_event(inc["id"], "dataops", "verify", f'hypothesis rejected: {top["text"]}')
            collab.add_comment(inc["id"], "Recommendation engine", "System",
                               f'Hypothesis rejected: {top["text"]} — seek an alternative cause.')
            st.session_state["flash"] = "Hypothesis rejected — recorded in history."
            st.rerun()
    return hyps


def _can_execute(role):
    return shell.can_execute(role)


def action_panel(inc, data):
    _role = st.session_state.get("you_role", "CSM")
    _may = _can_execute(_role)
    st.markdown("#### Act — repair   ·   **SIMULATED**")
    st.markdown('<span class="ri-tag" style="background:#dc2626">Execution — human approval</span> '
                '<span style="color:#64748b;font-size:12px">(this changes production, so it is risk-gated)</span>',
                unsafe_allow_html=True)
    st.caption("The outcome depends on the action chosen; verification is independent. Approval is enforced for "
               "high-risk actions.")
    labels = [f'{o["id"]} · {o["label"][:60]}{"…" if len(o["label"]) > 60 else ""}' for o in DE.DOP_REMEDIATION]
    sel = st.radio("Repair option", labels, key="dop_opt_" + inc["id"])
    opt = DE.DOP_REMEDIATION[labels.index(sel)]
    approved = True
    if opt["mode"] in ("Human approval", "Policy controlled"):
        st.warning(f'**{opt["mode"]} required** — {opt["label"]}')
        approved = st.checkbox("I approve this action (required before execution)", key="dop_appr_" + inc["id"])
    else:
        st.info(f'**{opt["mode"]}** — {opt["label"]}')
    if not _may:
        st.caption(f'Read-only for **{_role}** — execution needs an Incident Manager or Data Owner. '
                   f'Switch persona to act.')
    _executed = journey.applied_action(inc["id"])
    _rec = journey.resolution_record(inc["id"])
    if _executed:
        st.info(f'Execution recorded · **{_executed}** · authoritative verdict '
                f'**{(_rec or {}).get("verdict", "—")}**. The same repair cannot run twice; re-run the '
                f'independent verification instead.')
    _same = _executed == opt["id"]
    if st.button("Execute as a new attempt" if (_executed and not _same) else "Apply selected repair (simulated)",
                 disabled=(not approved) or (not _may) or bool(_executed and _same),
                 type=("primary" if collab.delegations(inc["id"]) else "secondary"),
                 key="dop_apply_" + inc["id"]):
        rows = DE.verification(inc, data, opt, True)
        v = journey.verdict(rows, True)
        st.session_state[f'dop_opt_applied_{inc["id"]}'] = opt["id"]
        st.session_state[f'verdict_{inc["id"]}'] = v
        DE.set_stage(inc["id"], {"Verified": "Validated", "Mitigated": "Fix applied",
                                 "Recovery failed": "Diagnosed"}.get(v, "Fix applied"))
        journey.set_resolution(inc["id"], v, action_id=opt["id"], checks=rows,
                               actor="Data-quality verification service")
        _attempt = " (attempt 2)" if _executed and not _same else ""
        journey.add_event(inc["id"], "dataops", "repair",
                          f'{opt["label"]}{_attempt} — independent verification: {v}')
        st.session_state["flash"] = f'Repair applied (simulated). Independent verification → **{v}**.'
        st.rerun()
    if _executed and st.button("Re-run independent verification", key="dop_reverify_" + inc["id"]):
        _rec_opt = next((o for o in DE.DOP_REMEDIATION if o["id"] == _executed), opt)
        rows = DE.verification(inc, data, _rec_opt, True)
        v = journey.verdict(rows, True)
        journey.set_resolution(inc["id"], v, action_id=_executed, checks=rows,
                               actor="Data-quality verification service")
        journey.add_event(inc["id"], "dataops", "verify", f'Verification re-run: {v}')
        st.session_state["flash"] = f'Verification re-run → **{v}**.'
        st.rerun()


def verify_panel(inc, data):
    st.markdown("#### Verify — independent verification")
    rec = journey.resolution_record(inc["id"])
    labels = [f'{o["id"]} · {o["label"][:60]}{"…" if len(o["label"]) > 60 else ""}' for o in DE.DOP_REMEDIATION]
    sel = st.session_state.get("dop_opt_" + inc["id"], labels[0])
    opt = DE.DOP_REMEDIATION[labels.index(sel)] if sel in labels else DE.DOP_REMEDIATION[0]
    if rec and rec.get("checks"):
        rows, applied_any, verdict = rec["checks"], True, rec["verdict"]
    else:
        applied = st.session_state.get(f'dop_opt_applied_{inc["id"]}') == opt["id"]
        rows = DE.verification(inc, data, opt, applied)
        applied_any = bool(st.session_state.get(f'dop_opt_applied_{inc["id"]}'))
        verdict = journey.verdict(rows, applied)
    journey.render_verification(rows, "Data-quality verification service")
    journey.render_verdict(verdict)
    st.caption("Simulated checks.")
    a = DE.analytics(inc, data)
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Incident age", f'{a["incident_age_min"]} min')
    a2.metric("Freshness lag", f'{a["freshness_lag_min"]} min')
    a3.metric("Data quality", a["quality"])
    a4.metric("Pipeline reliability", f'{a["reliability_pct"]}%')
    fresh_txt, _, _, _ = _fresh(data, inc["dataset_id"])
    journey.render_resolution(inc["id"], applied_any, f'freshness {fresh_txt}', inc["owner_team"], verdict=verdict)
    if applied_any:
        journey.render_recovery_by_verdict(
            "Data Owner update", verdict,
            restored="payments_gold refreshed — freshness within SLA and downstream consumers healthy. "
                     "Outcome independently verified.",
            partial="Partial recovery only — freshness improved but downstream is NOT fully healthy; repair ongoing.",
            failed="The repair did NOT restore freshness/quality — escalated.")


# ---------------------------------------------------------------- personas
def pipeline_view(inc, data, fns_only=False):
    """One scroll: the pipeline incident with every stage as a section, all anchors kept."""
    context_header(inc, data)

    def detect():
        with st.expander("Detection", expanded=True):
            journey.render_detection(inc["id"], "Data observability")
        with st.expander("Operational timeline", expanded=False):
            journey.render_timeline(inc["id"], limit=6)
        with st.expander("The pipeline story (lineage)", expanded=False):
            labels = {d: data["datasets"][d]["name"] for d in data["datasets"]}
            stale = tuple(d for d in data["datasets"] if _fresh(data, d)[1])
            viz.chain(DE.lineage_paths(inc["dataset_id"], data["G"])[0], labels,
                      stale=stale, highlight=(inc["dataset_id"],))
            st.info(inc["summary"])
        with st.expander("📉 Failure impact", expanded=False):
            downs, cons = DE.impact(inc["dataset_id"], data)
            st.write("**Downstream datasets:** " + (", ".join(data["datasets"][d]["name"] for d in downs) or "—"))
            st.write("**Consumers impacted:** " + (", ".join(cons) or "—"))

    def triage():
        fresh_txt, breach, lag, sla = _fresh(data, inc["dataset_id"])
        ds = data["datasets"].get(inc["dataset_id"], {}).get("name", inc["dataset_id"])
        ola = next((o for o in DE.load_olas() if o["team"] == inc["owner_team"]), None) if hasattr(DE, "load_olas") else None
        rec = DE.recommend(inc, DE.causes(inc, data), data)
        st.markdown(f'**Routing** — next engineer **{rec["actor"]}** · repair *{rec["action"]}* · '
                    f'gate **{rec["mode"]}**')
        st.markdown("**First response**")
        for step in [f'Check the latest run for {data["pipelines"].get(inc["pipeline_id"], {}).get("name", inc["pipeline_id"])}',
                     f'Confirm whether {ds} is inside its freshness SLA',
                     "Check the data contract before replaying anything",
                     "Escalate to the Data Owner once the blast radius is known"]:
            st.write(f'- {step}')
        handoff(f'to the Data Owner — {ds} · owner {inc["owner_team"]} · freshness {fresh_txt}.')

    def investigate():
        with st.expander("Operational timeline", expanded=True):
            journey.render_timeline(inc["id"])
        with st.expander("Lineage and affected datasets", expanded=False):
            labels = {d: data["datasets"][d]["name"] for d in data["datasets"]}
            stale = tuple(d for d in data["datasets"] if _fresh(data, d)[1])
            viz.chain(DE.lineage_paths(inc["dataset_id"], data["G"])[0], labels,
                      stale=stale, highlight=(inc["dataset_id"],))
        with st.expander("Failing run and data quality", expanded=False):
            run = DE.latest_run(inc["pipeline_id"], data["runs"])
            if run:
                st.markdown(f'**Latest run:** {run["id"]} · **{run["status"]}** · {run["started_at"]} · '
                            f'{run["duration_min"]} min' + (f' · `{run["error"]}`' if run["error"] else ''))
            breaches = _dq(data, inc["dataset_id"])
            if breaches:
                viz.card_rows([{"rule": d["rule"], "value": d["value"], "threshold": d["threshold"]}
                               for d in breaches], "#d97706")
            else:
                st.caption("No data-quality rule breaching on this dataset.")
        with st.expander("Downstream consumers", expanded=False):
            downs, cons = DE.impact(inc["dataset_id"], data)
            st.write("**Datasets:** " + (", ".join(data["datasets"][d]["name"] for d in downs) or "—"))
            st.write("**Consumers:** " + (", ".join(cons) or "—"))

    def correlate():
        with st.expander("🎯 Pipeline RCA — hypotheses", expanded=True):
            hypotheses(inc, data, limit=None)
        journey.render_correlation(inc["id"])

    def act():
        with st.expander("Recommended repair (policy-governed)", expanded=True):
            rec = DE.recommend(inc, DE.causes(inc, data), data)
            viz.rec_card(rec["action"], rec["risk"], rec["mode"], journey.actors(rec))
            journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
        action_panel(inc, data)

    def close():
        _gate = journey.closure_state(inc)
        _asks = [d for d in collab.delegations(inc["id"]) if d["status"] != "done"]

        def _finish(d):
            collab.set_delegation_status(d["id"], "done", actor=d["to_"])
            st.session_state["flash"] = f'Marked done — {d["to_"]} replied on the thread (simulated).'

        viz.closure_gate(_gate, on_close=lambda: journey.close_incident(inc["id"], "Incident Manager"),
                         asks=_asks, on_done=_finish, prefix="dop_close_step")
        with st.expander("Closure record", expanded=False):
            rec = journey.resolution_record(inc["id"])
            applied_any = bool(rec and rec.get("checks")) or bool(
                st.session_state.get(f'dop_opt_applied_{inc["id"]}'))
            fresh_txt0, _, _, _ = _fresh(data, inc["dataset_id"])
            journey.render_resolution(inc["id"], applied_any, f'freshness {fresh_txt0}',
                                      inc["owner_team"], verdict=journey.current_verdict(inc))

    def learn_stage():
        import learn
        learn.panel(inc, "DataOps", actor=st.session_state.get("you_role", "Data Owner"))

    stage_fns = {"Detect": detect, "Triage": triage, "Investigate": investigate,
                 "Correlate": correlate, "Act": act, "Verify": lambda: verify_panel(inc, data),
                 "Close": close, "Learn": learn_stage}
    if fns_only:
        return stage_fns
    sections.accordion_stages(inc, stage_fns, DOP_STEP_HELP, DOP_HANDOFFS, "dop_step")


def stage_functions(inc, data):
    """The stage bodies on their own, for the v107 tab that renders one at a time."""
    return pipeline_view(inc, data, fns_only=True)


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
                 "status": "Breach" if breach else "OK"})
    for d in downs:
        ft, br, _, _ = _fresh(data, d)
        rows.append({"dataset": data["datasets"][d]["name"], "freshness": ft, "status": "Breach" if br else "OK"})
    viz.card_rows(rows, "#0d9488")
    if st.session_state.get(f'dop_opt_applied_{inc["id"]}') or journey.applied_action(inc["id"]):
        journey.render_recovery_by_verdict(
            "Data Owner update", journey.current_verdict(inc),
            restored="payments_gold refreshed — freshness within SLA; downstream consumers "
                     "(Payment service (checkout-api), Finance close) healthy.",
            partial="Partial recovery only — freshness improved but downstream consumers are NOT fully healthy; repair ongoing.",
            failed="The repair did NOT restore freshness/quality — escalated; the incident remains open.")
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
