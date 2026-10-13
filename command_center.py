#!/usr/bin/env python3
"""Incident-first command center — the RESOLUTION THREAD is the core object.
Lifecycle is the single progress model; tabs are views of the same thread;
verification is an auditable record; closure only when independently Verified."""
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

THREAD = ["Detect", "Correlate", "Coordinate", "Verify", "Close"]


def _metric_label(m):
    return m.replace("_pct", "").replace("_", " ").strip().capitalize()


def _rail(inc, rec):
    st.markdown("#### 📡 Live event feed · simulated")
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
                           "Notified CSM with current status and business impact.")
        st.session_state["flash"] = "CSM notified (simulated)."
        st.rerun()
    if st.button("Post status update (simulated)", key="qa_upd_" + inc["id"]):
        collab.add_comment(inc["id"], "Recommendation engine", "System",
                           "Posted a status update to the incident thread.")
        st.session_state["flash"] = "Status update posted (simulated)."
        st.rerun()
    st.markdown("#### 🕒 Recent activity")
    for cm in collab.comments(inc["id"])[-4:]:
        st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')


def _thread_spine(deleg, confirmed, verdict):
    return [
        ("Detect", "done", "Incident and upstream pipeline failure detected", "5m"),
        ("Correlate", "done" if confirmed else "current",
         "Schema mismatch → stale data → affected service (hypothesis)", "15m"),
        ("Coordinate", "done" if deleg else "current", "Assign owner, approvals, remediation", "15m"),
        ("Verify", "done" if verdict == "Verified" else ("current" if deleg else "todo"),
         "Observed value vs threshold + verifying actor", "30m"),
        ("Close", "done" if verdict == "Verified" else ("current" if verdict in ("Mitigated", "Recovery failed") else "todo"),
         "Verified / Mitigated / Recovery failed", None),
    ]


def it_command(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    chain = E.dependency_paths(G, inc["service_id"])[0]
    biz = E.business_service(G, chain, services)
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    sla_txt, rem, target, elapsed = P._sla_detail(inc)
    verdict = st.session_state.get(f'verdict_{inc["id"]}', "Investigating")
    deleg = bool(collab.delegations(inc["id"]))
    confirmed = any(c["status"] == "confirmed" for c in causes)
    corr = journey.correlation_for(inc["id"])
    refs = [inc["id"]] + ([corr["other_id"]] if corr else [])
    k = P._kpi(ctx, biz)
    bizname = services[biz]["name"] if biz else "—"

    meta = (f'Service {services[inc["service_id"]]["name"]} · Business impact {bizname} · '
            f'Owner {inc["owner_team"]} · Elapsed {int(elapsed)}m')
    viz.hero(inc["priority"], inc["id"], inc["title"], meta, sla_txt, verdict,
             ["IT Ops", "Cross-Domain", "ServiceNow · Jira"])

    st.markdown("#### Lifecycle — the single progress model")
    viz.stepper(P.STAGES, inc["stage"])
    st.markdown("#### Resolution thread")
    viz.thread_spine(_thread_spine(deleg, confirmed, verdict))
    st.caption("Each stage carries an internal **OLA** (owner-team target) — distinct from the customer **SLA** "
               "in the header. Set per team and per stage.")
    if corr:
        st.caption(f'🔗 Thread links **IT Ops {inc["id"]}** ↔ **DataOps {corr["other_id"]}** · '
                   f'shared cause **{corr["shared_cause"]}**.')

    tab_labels = ["Overview", "Investigation", "Impact", "Collaboration", "Verification", "Timeline"]
    main, rail = st.columns([2.4, 1])
    with main:
        t = st.tabs(tab_labels)
        with t[0]:
            vcol = {"Verified": "#16a34a", "Mitigated": "#d97706", "Recovery failed": "#dc2626"}.get(
                verdict, "#2563eb")
            viz.kpi_row([
                ("Business impact", bizname, "customer-facing", "#dc2626"),
                ("Status", verdict, inc["stage"], vcol),
                ("Next owner", rec["actor"], f'gate: {rec["mode"]}', "#0891b2"),
                ("Next action", (rec["action"][:64] + ("…" if len(rec["action"]) > 64 else "")),
                 "recommended", "#4f46e5"),
            ])
            st.markdown("#### What connects the failure (cross-domain)")
            if corr:
                viz.causal([("Schema mismatch", "DataOps"), ("Pipeline failure", "DataOps"),
                            ("Stale payments data", "DataOps"), ("Payment API impact", "IT Ops")])
                st.caption(f'🔗 IT Ops **{inc["id"]}** ↔ DataOps **{corr["other_id"]}** · shared cause '
                           f'**{corr["shared_cause"]}** · evidence flows left → right.')
            else:
                viz.chain(chain, {n: services[n]["name"] for n in services}, highlight=(inc["service_id"],))
            st.info(inc["summary"])
            if k:
                viz.impact_summary(_metric_label(k["metric"]), k["baseline"], k["current"], k["unit"],
                                   "incident onset", inc["created_at"].split("T")[-1][:5])
            st.caption(f'Affected service: {services[inc["service_id"]]["name"]} '
                       f'({services[inc["service_id"]]["type"].replace("_"," ")})')
        with t[1]:
            P.hypotheses(inc, ctx)
            with st.expander("Related incidents"):
                for s in (E.similar(incidents, inc) or [f'None above threshold ({E.SIMILARITY_THRESHOLD}).']):
                    st.write(f'- {s}')
            with st.expander("Change risk"):
                ch = E.latest_change(inc, G, changes)
                if ch:
                    cr = E.change_risk(ch, G, services, incidents)
                    st.write(f'**{ch["id"]}** · {ch["description"]} · risk **{cr["risk"]}** (gate {cr["gate"]})')
        with t[2]:
            st.markdown("#### Cross-domain causal chain")
            if corr:
                viz.causal([("Schema mismatch", "DataOps"), ("Pipeline failure", "DataOps"),
                            ("Stale payments data", "DataOps"), ("Payment API impact", "IT Ops")])
            st.markdown("#### Dependency & impact path (IT service)")
            viz.chain(chain, {n: services[n]["name"] for n in services}, highlight=(inc["service_id"],))
            if k:
                viz.impact_summary(_metric_label(k["metric"]), k["baseline"], k["current"], k["unit"],
                                   "incident onset", inc["created_at"].split("T")[-1][:5])
        with t[3]:
            st.markdown("#### Team & ownership")
            st.markdown(f'- **{inc["owner_team"]}** — owner')
            for a in journey.actors(rec):
                st.markdown(f'- {a} — next actor')
            journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
            for cm in collab.comments(inc["id"]):
                st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')
        with t[4]:
            labels = [f'{o["id"]} · {o["label"]}' for o in E.IT_REMEDIATION]
            sel = st.session_state.get("it_opt_" + inc["id"], labels[0])
            opt = E.IT_REMEDIATION[labels.index(sel)] if sel in labels else E.IT_REMEDIATION[0]
            applied = st.session_state.get(f'it_opt_applied_{inc["id"]}') == opt["id"]
            rows = E.it_verification(inc, ctx, opt, applied)
            ts = dt.datetime.now().strftime("%H:%M")
            audit = [{"check": r["check"], "observed": r["after (simulated)"],
                      "threshold": r["threshold checked"], "at": ts,
                      "by": "SRE verification service", "result": r["result"]} for r in rows]
            viz.audit_record(audit, inc["id"])
            journey.render_verdict(journey.verdict(rows, applied))
            applied_any = bool(st.session_state.get(f'it_opt_applied_{inc["id"]}'))
            journey.render_resolution(inc["id"], applied_any, sla_txt, inc["owner_team"], verdict=verdict)
            if applied_any and verdict == "Verified":
                journey.render_recovery_update("Recovery update — evidence-backed",
                                               "Service restored; outcome independently verified. (Simulated.)")
            elif applied_any and verdict in ("Mitigated", "Recovery failed"):
                journey.render_recovery_update("Update — not a closure",
                                               f'Verification outcome: **{verdict}** — the incident remains open. '
                                               f'(Simulated.)',
                                               kind=("warning" if verdict == "Mitigated" else "error"))
        with t[5]:
            st.markdown("#### Canonical timeline — one history across both domains")
            viz.timeline(journey.timeline_multi(refs))
    with rail:
        _rail(inc, rec)


def dop_command(inc, data):
    ds = inc["dataset_id"]
    chain = DE.lineage_paths(ds, data["G"])[0]
    fresh_txt, breach, lag, sla = DV._fresh(data, ds)
    causes = DE.causes(inc, data)
    rec = DE.recommend(inc, causes, data)
    verdict = st.session_state.get(f'verdict_{inc["id"]}', "Investigating")
    deleg = bool(collab.delegations(inc["id"]))
    confirmed = any(c["status"] == "confirmed" for c in causes)
    corr = journey.correlation_for(inc["id"])
    refs = [inc["id"]] + ([corr["other_id"]] if corr else [])
    downs, cons = DE.impact(ds, data)
    try:
        elapsed = int((dt.datetime.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 60)
    except Exception:
        elapsed = 0
    meta = (f'Pipeline {inc["pipeline_id"]} · Dataset {data["datasets"][ds]["name"]} · '
            f'Owner {inc["owner_team"]} · Elapsed {elapsed}m')
    viz.hero(inc["priority"], inc["id"], inc["title"], meta, fresh_txt, verdict,
             ["DataOps", "Cross-Domain", "Lineage + DQ"])
    st.markdown("#### Lifecycle — the single progress model")
    viz.stepper(DE.STAGES, inc["stage"])
    st.markdown("#### Resolution thread")
    viz.thread_spine(_thread_spine(deleg, confirmed, verdict))
    st.caption("Each stage carries an internal **OLA** (owner-team target) — distinct from the customer **SLA** "
               "in the header. Set per team and per stage.")
    if corr:
        st.caption(f'🔗 Thread links **DataOps {inc["id"]}** ↔ **IT Ops {corr["other_id"]}** · '
                   f'shared cause **{corr["shared_cause"]}**.')

    main, rail = st.columns([2.4, 1])
    with main:
        t = st.tabs(["Overview", "Investigation", "Impact", "Collaboration", "Verification", "Timeline"])
        with t[0]:
            viz.kpi_row([
                ("Pipeline", inc["pipeline_id"], "producer", "#dc2626"),
                ("Freshness", fresh_txt, "SLA breach" if breach else "within SLA", "#d97706"),
                ("Consumers", str(len(cons)), "downstream", "#7c3aed"),
                ("Top hypothesis", (causes[0]["type"].title() if causes else "—"),
                 (f'{causes[0]["confidence"]} confidence' if causes else ""), "#d97706"),
            ])
            st.info(inc["summary"])
        with t[1]:
            DV.hypotheses(inc, data)
        with t[2]:
            st.markdown("#### Pipeline lineage")
            stale = tuple(d for d in data["datasets"] if DV._fresh(data, d)[1])
            viz.chain(chain, {d: data["datasets"][d]["name"] for d in data["datasets"]},
                      stale=stale, highlight=(ds,))
            st.markdown("**Consumers impacted:** " + (", ".join(cons) or "—"))
        with t[3]:
            journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
            for cm in collab.comments(inc["id"]):
                st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')
        with t[4]:
            labels = [f'{o["id"]} · {o["label"]}' for o in DE.DOP_REMEDIATION]
            sel = st.session_state.get("dop_opt_" + inc["id"], labels[0])
            opt = DE.DOP_REMEDIATION[labels.index(sel)] if sel in labels else DE.DOP_REMEDIATION[0]
            applied = st.session_state.get(f'dop_opt_applied_{inc["id"]}') == opt["id"]
            rows = DE.verification(inc, data, opt, applied)
            ts = dt.datetime.now().strftime("%H:%M")
            audit = [{"check": r["check"], "observed": r["after (simulated)"],
                      "threshold": r["threshold checked"], "at": ts,
                      "by": "Data-quality verification service", "result": r["result"]} for r in rows]
            viz.audit_record(audit, inc["id"])
            journey.render_verdict(journey.verdict(rows, applied))
            applied_any = bool(st.session_state.get(f'dop_opt_applied_{inc["id"]}'))
            journey.render_resolution(inc["id"], applied_any, f'freshness {fresh_txt}', inc["owner_team"],
                                      verdict=verdict)
            if applied_any and verdict == "Verified":
                journey.render_recovery_update("Recovery update — evidence-backed",
                                               "Freshness and quality restored; outcome independently verified. (Simulated.)")
            elif applied_any and verdict in ("Mitigated", "Recovery failed"):
                journey.render_recovery_update("Update — not a closure",
                                               f'Verification outcome: **{verdict}** — the incident remains open. '
                                               f'(Simulated.)',
                                               kind=("warning" if verdict == "Mitigated" else "error"))
        with t[5]:
            st.markdown("#### Canonical timeline — one history across both domains")
            viz.timeline(journey.timeline_multi(refs))
    with rail:
        st.markdown("#### 📡 Live event feed · simulated")
        viz.feed(realtime.recent(8))
        st.markdown("#### 👥 Team & ownership")
        st.markdown(f'- **{inc["owner_team"]}** — owner')
        for a in journey.actors(rec):
            st.markdown(f'- {a} — next actor')
        st.markdown("#### 🕒 Recent activity")
        for cm in collab.comments(inc["id"])[-4:]:
            st.markdown(f'**{cm["author"]}** · _{cm["ts"][11:16]}_  \n{cm["text"]}')
