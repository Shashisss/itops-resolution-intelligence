#!/usr/bin/env python3
"""Incident workspace — the RESOLUTION THREAD is the core object.
One shared layout (see workspace.render_workspace) for IT Ops and DataOps; only the evidence,
hypotheses and actions differ. Lifecycle is the single progress model; verification is an
auditable record; closure only when independently Verified."""
import datetime as dt
import streamlit as st
import engine as E
import personas as P
import dataops_views as DV
import dataops_engine as DE
import journey
import viz
import collab
import realtime
import workspace


def _metric_label(m):
    return m.replace("_pct", "").replace("_", " ").strip().capitalize()


# Resolution-acceleration metrics (ILLUSTRATIVE — baseline vs with-platform). Honest framing:
# simulated demo values; measure against a real baseline in a pilot.
IMPACT_ROWS = [
    ("MTTR — mean time to resolution", "~4 h 10 m", "~1 h 05 m"),
    ("Time to identify likely cause", "~45 min", "~10 min"),
    ("Time to assign next owner (coordination)", "~30 min", "~2 min"),
    ("Time to verified recovery", "~4 h", "~1 h"),
    ("Handoffs auto-coordinated", "0%", "~70%"),
    ("SLA / OLA breaches (per month)", "6", "2"),
    ("Repeat incidents (per month)", "12", "5"),
    ("Operator effort (person-hours)", "9", "3"),
]


def _rail(inc, rec):
    """Shared right-hand rail (identical for IT Ops and DataOps)."""
    with st.expander("📡 Live event feed · simulated", expanded=False):
        viz.feed(realtime.recent(8))
    st.markdown("#### 👥 Team & ownership")
    st.markdown(f'- **{inc["owner_team"]}** — owner')
    for a in journey.actors(rec):
        st.markdown(f'- {a} — next actor')
    for c in collab.collaborators()[:3]:
        st.markdown(f'- {c["who"]} — {c["role"]}')
    st.markdown("#### ⚡ Quick actions")
    if st.button("Notify CSM (simulated)", key="qa_csm_" + inc["id"]):
        collab.add_comment(inc["id"], "Recommendation engine", "System",
                           "[Demo] Logged a CSM notification locally — no external message was sent.")
        st.session_state["flash"] = "CSM notification logged (simulated, local only)."
        st.rerun()
    if st.button("Post status update (simulated)", key="qa_upd_" + inc["id"]):
        collab.add_comment(inc["id"], "Recommendation engine", "System",
                           "[Demo] Added a status update to the incident thread (local only).")
        st.session_state["flash"] = "Status update posted to the thread (simulated, local only)."
        st.rerun()
    with st.expander("🕒 Recent activity", expanded=False):
        cms = collab.comments(inc["id"])[-6:]
        if not cms:
            st.caption("No activity yet.")
        for cm in cms:
            st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')


def _stage_ola_live(inc, stage, target):
    now = dt.datetime.now()
    start = None
    if stage in ("Detect", "Correlate"):
        try:
            start = dt.datetime.fromisoformat(inc["created_at"])
        except Exception:
            start = None
    elif stage == "Coordinate":
        ds = collab.delegations(inc["id"])
        if ds:
            try:
                start = dt.datetime.fromisoformat(ds[0]["ts"])
            except Exception:
                start = None
    elif stage in ("Verify", "Close"):
        ev = [x for x in journey.timeline(inc["id"]) if x["kind"] == "repair"]
        if ev:
            try:
                start = dt.datetime.fromisoformat(ev[-1]["ts"])
            except Exception:
                start = None
    if start is None:
        return f'{target}m'
    rem = target - (now - start).total_seconds() / 60
    return f'{target}m · ' + ("BREACHED" if rem <= 0 else f'{int(rem)}m left')


def _thread_spine(inc, deleg, confirmed, verdict):
    olas = {o["stage"]: o["target_min"] for o in E.load_stage_olas()}
    applied = bool(journey.applied_action(inc["id"]))
    # Status is derived from EVIDENCE, not stage names: a confirmed hypothesis is not "Correlate complete",
    # and applying a fix is not "Verified". Closure only on Verified.
    stages = [
        ("Detect", "done", "Incident and upstream failure detected", "Detect"),
        ("Correlate", "done", "Cross-domain link — ranked hypotheses (observed vs inferred)", "Correlate"),
        ("Coordinate", "done" if deleg else "current", "Owner assigned, approvals, remediation", "Coordinate"),
        ("Act", "done" if applied else ("current" if deleg else "todo"),
         "Remediation executed under approval (simulated)", "Act"),
        ("Verify", "done" if verdict == "Verified" else ("current" if applied else "todo"),
         "Independent re-check vs thresholds + verifying actor", "Verify"),
        ("Close", "done" if verdict == "Verified" else ("current" if verdict in ("Mitigated", "Recovery failed") else "todo"),
         "Verified / Mitigated / Recovery failed", "Close"),
    ]
    cur = next((s[0] for s in stages if s[1] == "current"), None)
    items = []
    for title, status, detail, key in stages:
        if key in olas:
            ola = _stage_ola_live(inc, key, olas[key]) if key == cur else f'{olas[key]}m'
        else:
            ola = None
        items.append((title, status, detail, ola))
    return items


# ================================================================= IT Ops workspace
def it_command(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    chain = E.dependency_paths(G, inc["service_id"])[0]
    biz = E.business_service(G, chain, services)
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    sla_txt, rem, target, elapsed = P._sla_detail(inc)
    verdict = journey.current_verdict(inc)
    deleg = bool(collab.delegations(inc["id"]))
    confirmed = any(c["status"] == "confirmed" for c in causes)
    corr = journey.correlation_for(inc["id"])
    refs = [inc["id"]] + ([corr["other_id"]] if corr else [])
    k = P._kpi(ctx, biz)
    bizname = services[biz]["name"] if biz else "—"

    hero_kwargs = dict(
        priority=inc["priority"], inc_id=inc["id"], title=inc["title"],
        meta=(f'Service {services[inc["service_id"]]["name"]} · Business impact {bizname} · '
              f'Owner {inc["owner_team"]} · Stage {journey.lifecycle_stage(inc)} · Elapsed {int(elapsed)}m'),
        sla_text=sla_txt, verdict=verdict, chips=["IT Ops", "Cross-Domain", "ServiceNow · Jira"])
    lifecycle = _thread_spine(inc, deleg, confirmed, verdict)
    edges = journey.thread_edges_for(inc["id"])

    def overview():
        vcol = {"Verified": "#16a34a", "Mitigated": "#d97706", "Recovery failed": "#dc2626"}.get(
            verdict, "#2563eb")
        viz.kpi_row([
            ("Business impact", bizname, "customer-facing", "#dc2626"),
            ("Status", verdict, journey.lifecycle_stage(inc), vcol),
            ("Next owner", rec["actor"], f'gate: {rec["mode"]}', "#0891b2"),
            ("Next action", (rec["action"][:64] + ("…" if len(rec["action"]) > 64 else "")),
             "recommended", "#4f46e5"),
        ])
        st.info(inc["summary"])
        if k:
            viz.impact_summary(_metric_label(k["metric"]), k["baseline"], k["current"], k["unit"],
                               "incident onset", inc["created_at"].split("T")[-1][:5])
        st.caption(f'Affected service: {services[inc["service_id"]]["name"]} '
                   f'({services[inc["service_id"]]["type"].replace("_", " ")})')
        viz.value_strip(IMPACT_ROWS)

    def investigation():
        P.hypotheses(inc, ctx)
        with st.expander("Related incidents"):
            for s in (E.similar(incidents, inc) or [f'None above threshold ({E.SIMILARITY_THRESHOLD}).']):
                st.write(f'- {s}')
        with st.expander("Change risk"):
            ch = E.latest_change(inc, G, changes)
            if ch:
                cr = E.change_risk(ch, G, services, incidents)
                st.write(f'**{ch["id"]}** · {ch["description"]} · risk **{cr["risk"]}** (gate {cr["gate"]})')

    def impact():
        st.markdown("#### Cross-domain causal chain")
        if corr:
            viz.causal([("Schema mismatch", "DataOps"), ("Pipeline failure", "DataOps"),
                        ("Stale payments data", "DataOps"), ("Payment API impact", "IT Ops")])
        st.markdown("#### Dependency & impact path (IT service)")
        viz.chain(chain, {n: services[n]["name"] for n in services}, highlight=(inc["service_id"],))
        if k:
            viz.impact_summary(_metric_label(k["metric"]), k["baseline"], k["current"], k["unit"],
                               "incident onset", inc["created_at"].split("T")[-1][:5])

    def collaboration():
        st.markdown("#### Team & ownership")
        st.markdown(f'- **{inc["owner_team"]}** — owner')
        for a in journey.actors(rec):
            st.markdown(f'- {a} — next actor')
        journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
        for cm in collab.comments(inc["id"]):
            st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')

    def verification():
        labels = [f'{o["id"]} · {o["label"]}' for o in E.IT_REMEDIATION]
        sel = st.session_state.get("it_opt_" + inc["id"], labels[0])
        opt = E.IT_REMEDIATION[labels.index(sel)] if sel in labels else E.IT_REMEDIATION[0]
        res = journey.resolution_record(inc["id"])
        if res and res.get("action_id"):
            opt = next((o for o in E.IT_REMEDIATION if o["id"] == res["action_id"]), opt)
        if res and res.get("checks"):
            rows = res["checks"]
        else:
            applied = st.session_state.get(f'it_opt_applied_{inc["id"]}') == opt["id"]
            rows = E.it_verification(inc, ctx, opt, applied)
        ts = dt.datetime.now().strftime("%H:%M")
        _srcmap = {"Latency (p95, ms)": "Observability", "Error rate (%)": "Observability",
                   "DB connections": "Observability"}
        audit = [{"check": r["check"], "source": _srcmap.get(r["check"], "Business KPI / warehouse"),
                  "action": f'{opt["id"]} · {opt["label"][:30]}', "observed": r["after (simulated)"],
                  "threshold": r["threshold checked"], "at": ts, "by": "SRE verification service",
                  "result": r["result"]} for r in rows]
        viz.audit_record(audit, inc["id"])
        journey.render_verdict(journey.current_verdict(inc))
        applied_any = bool(res and res.get("checks")) or bool(st.session_state.get(f'it_opt_applied_{inc["id"]}'))
        journey.render_resolution(inc["id"], applied_any, sla_txt, inc["owner_team"], verdict=verdict)
        if applied_any:
            journey.render_recovery_by_verdict(
                "Recovery update", journey.current_verdict(inc),
                restored="Service restored; outcome independently verified.",
                partial="Partial recovery only — the incident remains open.",
                failed="Recovery failed — the incident remains open; escalate.")

    def timeline():
        st.markdown("#### Canonical timeline — one history across both domains")
        viz.timeline(journey.timeline_multi(refs))

    workspace.render_workspace(
        hero_kwargs, lifecycle, edges,
        {"Overview": overview, "Investigation": investigation, "Impact": impact,
         "Collaboration": collaboration, "Verification": verification, "Timeline": timeline},
        rail=lambda: _rail(inc, rec), corr=corr,
        collab_banner=(lambda: viz.collab_strip(inc["owner_team"],
                                               (journey.actors(rec) or ["—"])[0],
                                               journey.collab_stats(inc))
                       if hasattr(viz, "collab_strip") and hasattr(journey, "collab_stats") else None))


# ================================================================= DataOps workspace
def dop_command(inc, data):
    ds = inc["dataset_id"]
    chain = DE.lineage_paths(ds, data["G"])[0]
    fresh_txt, breach, lag, sla = DV._fresh(data, ds)
    causes = DE.causes(inc, data)
    rec = DE.recommend(inc, causes, data)
    verdict = journey.current_verdict(inc)
    deleg = bool(collab.delegations(inc["id"]))
    confirmed = any(c["status"] == "confirmed" for c in causes)
    corr = journey.correlation_for(inc["id"])
    refs = [inc["id"]] + ([corr["other_id"]] if corr else [])
    downs, cons = DE.impact(ds, data)
    try:
        elapsed = int((dt.datetime.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 60)
    except Exception:
        elapsed = 0

    hero_kwargs = dict(
        priority=inc["priority"], inc_id=inc["id"], title=inc["title"],
        meta=(f'Pipeline {inc["pipeline_id"]} · Dataset {data["datasets"][ds]["name"]} · '
              f'Owner {inc["owner_team"]} · Stage {journey.lifecycle_stage(inc)} · Elapsed {elapsed}m'),
        sla_text=fresh_txt, verdict=verdict, chips=["DataOps", "Cross-Domain", "Lineage + DQ"])
    lifecycle = _thread_spine(inc, deleg, confirmed, verdict)
    edges = journey.thread_edges_for(inc["id"])

    def overview():
        viz.kpi_row([
            ("Pipeline", inc["pipeline_id"], "producer", "#dc2626"),
            ("Freshness", fresh_txt, "SLA breach" if breach else "within SLA", "#d97706"),
            ("Consumers", str(len(cons)), "downstream", "#7c3aed"),
            ("Top hypothesis", (causes[0].get("label") or causes[0]["type"].title() if causes else "—"),
             (f'{causes[0]["confidence"]} confidence' if causes else ""), "#d97706"),
        ])
        st.info(inc["summary"])
        st.caption(f'Downstream datasets: {", ".join(data["datasets"][d]["name"] for d in downs) or "—"}')
        viz.value_strip(IMPACT_ROWS)

    def investigation():
        DV.hypotheses(inc, data)

    def impact():
        st.markdown("#### Pipeline lineage")
        stale = tuple(d for d in data["datasets"] if DV._fresh(data, d)[1])
        viz.chain(chain, {d: data["datasets"][d]["name"] for d in data["datasets"]},
                  stale=stale, highlight=(ds,))
        st.markdown("**Consumers impacted:** " + (", ".join(cons) or "—"))

    def collaboration():
        st.markdown("#### Team & ownership")
        st.markdown(f'- **{inc["owner_team"]}** — owner')
        for a in journey.actors(rec):
            st.markdown(f'- {a} — next actor')
        journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
        for cm in collab.comments(inc["id"]):
            st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')

    def verification():
        labels = [f'{o["id"]} · {o["label"]}' for o in DE.DOP_REMEDIATION]
        sel = st.session_state.get("dop_opt_" + inc["id"], labels[0])
        opt = DE.DOP_REMEDIATION[labels.index(sel)] if sel in labels else DE.DOP_REMEDIATION[0]
        res = journey.resolution_record(inc["id"])
        if res and res.get("action_id"):
            opt = next((o for o in DE.DOP_REMEDIATION if o["id"] == res["action_id"]), opt)
        if res and res.get("checks"):
            rows = res["checks"]
        else:
            applied = st.session_state.get(f'dop_opt_applied_{inc["id"]}') == opt["id"]
            rows = DE.verification(inc, data, opt, applied)
        ts = dt.datetime.now().strftime("%H:%M")

        def _src(chk):
            if chk.startswith("Freshness"):
                return "DataOps freshness"
            if chk.startswith("DQ"):
                return "DataOps quality"
            if chk.startswith("Downstream"):
                return "Lineage / downstream health"
            return "DataOps"

        audit = [{"check": r["check"], "source": _src(r["check"]),
                  "action": f'{opt["id"]} · {opt["label"][:28]}', "observed": r["after (simulated)"],
                  "threshold": r["threshold checked"], "at": ts, "by": "Data-quality verification service",
                  "result": r["result"]} for r in rows]
        viz.audit_record(audit, inc["id"])
        journey.render_verdict(journey.current_verdict(inc))
        applied_any = bool(res and res.get("checks")) or bool(st.session_state.get(f'dop_opt_applied_{inc["id"]}'))
        journey.render_resolution(inc["id"], applied_any, f'freshness {fresh_txt}', inc["owner_team"],
                                  verdict=verdict)
        if applied_any:
            journey.render_recovery_by_verdict(
                "Recovery update", journey.current_verdict(inc),
                restored="Freshness and quality restored; outcome independently verified.",
                partial="Partial recovery only — the incident remains open.",
                failed="Recovery failed — the incident remains open; escalate.")

    def timeline():
        st.markdown("#### Canonical timeline — one history across both domains")
        viz.timeline(journey.timeline_multi(refs))

    workspace.render_workspace(
        hero_kwargs, lifecycle, edges,
        {"Overview": overview, "Investigation": investigation, "Impact": impact,
         "Collaboration": collaboration, "Verification": verification, "Timeline": timeline},
        rail=lambda: _rail(inc, rec), corr=corr,
        collab_banner=(lambda: viz.collab_strip(inc["owner_team"],
                                               (journey.actors(rec) or ["—"])[0],
                                               journey.collab_stats(inc))
                       if hasattr(viz, "collab_strip") and hasattr(journey, "collab_stats") else None))
