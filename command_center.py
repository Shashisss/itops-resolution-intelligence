#!/usr/bin/env python3
"""Incident-first command center — hero header, tabbed canvas, persistent live rail.
Reuses the same governed record and truthful verification as the guided journey."""
import streamlit as st
import engine as E
import personas as P
import dataops_views as DV
import dataops_engine as DE
import journey
import viz
import collab
import realtime


def _rail(inc, ctx, rec):
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


def it_command(inc, ctx):
    services, changes, metrics, incidents, G = (ctx["services"], ctx["changes"], ctx["metrics"],
                                                 ctx["incidents"], ctx["G"])
    chain = E.dependency_paths(G, inc["service_id"])[0]
    biz = E.business_service(G, chain, services)
    causes = E.causes(inc, G, changes, metrics, services)
    rec = E.recommend(inc, causes)
    sla_txt, rem, target, elapsed = P._sla_detail(inc)
    verdict = st.session_state.get(f'verdict_{inc["id"]}', "Investigating")
    k = P._kpi(ctx, biz)
    bizname = services[biz]["name"] if biz else "—"
    meta = (f'Service {services[inc["service_id"]]["name"]} · Business impact {bizname} · '
            f'Owner {inc["owner_team"]} · Elapsed {int(elapsed)}m')
    viz.hero(inc["priority"], inc["id"], inc["title"], meta, sla_txt, verdict,
             ["IT Ops", "Cross-Domain", "ServiceNow · Jira"])

    main, rail = st.columns([2.4, 1])
    with main:
        t = st.tabs(["Overview", "Investigation", "Recommendations", "Verification", "Timeline"])
        with t[0]:
            viz.kpi_row([
                ("Affected service", services[inc["service_id"]]["name"], "IT service", "#dc2626"),
                ("Business impact", bizname, "customer-facing", "#dc2626"),
                ("Business KPI", (f'{k["metric"].replace("_"," ")} {k["current"]:.0f}{k["unit"]}' if k else "n/a"),
                 (f'baseline {k["baseline"]:.1f}{k["unit"]}' if k else ""), "#7c3aed"),
                ("Top hypothesis", (causes[0]["type"].title() if causes else "—"),
                 (f'{causes[0]["confidence"]} confidence' if causes else ""), "#d97706"),
            ])
            st.markdown("#### The operational story")
            st.write(" → ".join(services[n]["name"] for n in chain))
            st.info(inc["summary"])
            st.markdown("#### Dependency & impact path")
            viz.chain(chain, {n: services[n]["name"] for n in services}, highlight=(inc["service_id"],))
            st.markdown("#### Business impact")
            df = P._kpi_df()
            st.line_chart(df[df.scenario == "current"].set_index("ts")["value"], height=140)
        with t[1]:
            P.hypotheses(inc, ctx)
            with st.expander("Related incidents"):
                for s in (E.similar(incidents, inc) or [f'None above the relevance threshold '
                                                        f'({E.SIMILARITY_THRESHOLD}).']):
                    st.write(f'- {s}')
            with st.expander("Change risk"):
                ch = E.latest_change(inc, G, changes)
                if ch:
                    cr = E.change_risk(ch, G, services, incidents)
                    st.write(f'**{ch["id"]}** · {ch["description"]} · risk **{cr["risk"]}** (gate {cr["gate"]})')
                else:
                    st.caption("No recent change in the impacted subgraph.")
        with t[2]:
            viz.rec_card(rec["action"], rec["risk"], rec["mode"], journey.actors(rec))
            journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
            P.action_panel(inc, ctx)
        with t[3]:
            P.verify_panel(inc, ctx)
        with t[4]:
            journey.render_timeline(inc["id"])
    with rail:
        _rail(inc, ctx, rec)


def dop_command(inc, data):
    ds = inc["dataset_id"]
    chain = DE.lineage_paths(ds, data["G"])[0]
    fresh_txt, breach, lag, sla = DV._fresh(data, ds)
    causes = DE.causes(inc, data)
    rec = DE.recommend(inc, causes, data)
    verdict = st.session_state.get(f'verdict_{inc["id"]}', "Investigating")
    downs, cons = DE.impact(ds, data)
    try:
        import datetime as dt
        elapsed = int((dt.datetime.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 60)
    except Exception:
        elapsed = 0
    meta = (f'Pipeline {inc["pipeline_id"]} · Dataset {data["datasets"][ds]["name"]} · '
            f'Owner {inc["owner_team"]} · Elapsed {elapsed}m')
    viz.hero(inc["priority"], inc["id"], inc["title"], meta, fresh_txt, verdict,
             ["DataOps", "Cross-Domain", "Lineage + DQ"])

    main, rail = st.columns([2.4, 1])
    with main:
        t = st.tabs(["Overview", "Investigation", "Recommendations", "Verification", "Timeline"])
        with t[0]:
            viz.kpi_row([
                ("Pipeline", inc["pipeline_id"], "producer", "#dc2626"),
                ("Freshness", fresh_txt, "SLA breach" if breach else "within SLA", "#d97706"),
                ("Consumers", str(len(cons)), "downstream", "#7c3aed"),
                ("Top hypothesis", (causes[0]["type"].title() if causes else "—"),
                 (f'{causes[0]["confidence"]} confidence' if causes else ""), "#d97706"),
            ])
            st.markdown("#### The pipeline story (lineage)")
            stale = tuple(d for d in data["datasets"] if DV._fresh(data, d)[1])
            viz.chain(chain, {d: data["datasets"][d]["name"] for d in data["datasets"]},
                      stale=stale, highlight=(ds,))
            st.info(inc["summary"])
            st.markdown("**Consumers impacted:** " + (", ".join(cons) or "—"))
        with t[1]:
            DV.hypotheses(inc, data)
        with t[2]:
            viz.rec_card(rec["action"], rec["risk"], rec["mode"], journey.actors(rec))
            journey.engage_block(inc["id"], rec["action"], journey.actors(rec))
            DV.action_panel(inc, data)
        with t[3]:
            DV.verify_panel(inc, data)
        with t[4]:
            journey.render_timeline(inc["id"])
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
