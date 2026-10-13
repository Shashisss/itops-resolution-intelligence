#!/usr/bin/env python3
"""Live Operations — real-time monitoring, collaboration and delegation (cross-domain)."""
import datetime as dt
import pandas as pd
import streamlit as st
import engine as E
import dataops_engine as DE
import realtime
import collab
import journey
import viz

ROLES = ["Incident Manager", "Data Engineer", "Data Owner", "Platform Engineer",
         "L2 / L3 Engineer", "Developer", "CSM"]
TEAMS = ["Data Engineer", "Data Owner", "Platform Engineer", "L2 / L3 Engineer", "Developer", "DBA Team"]
SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24}


def _sla(inc):
    try:
        hrs = SLA_HOURS.get(inc["priority"], 8) - (dt.datetime.now() -
              dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 3600
        return ("BREACHED" if hrs <= 0 else f"{int(hrs)}h {int((hrs % 1) * 60)}m"), hrs
    except Exception:
        return "n/a", None


def _rec(ref, it, ddata):
    if ref.startswith("INC"):
        inc = next(i for i in it["incidents"] if i["id"] == ref)
        return E.recommend(inc, E.causes(inc, it["G"], it["changes"], it["metrics"], it["services"]))
    inc = next(i for i in ddata["incidents"] if i["id"] == ref)
    return DE.recommend(inc, DE.causes(inc, ddata), ddata)


def _find(ref, it, ddata):
    if ref.startswith("INC"):
        return next(i for i in it["incidents"] if i["id"] == ref)
    return next(i for i in ddata["incidents"] if i["id"] == ref)


def _sla_countdown(ref, it, ddata):
    def render():
        inc = _find(ref, it, ddata)
        target = SLA_HOURS.get(inc["priority"], 8) * 3600
        try:
            elapsed = (dt.datetime.now() - dt.datetime.fromisoformat(inc["created_at"])).total_seconds()
        except Exception:
            elapsed = 0
        rem = max(0, target - elapsed)
        pct = max(0.0, min(1.0, rem / target))
        h, m, s = int(rem // 3600), int((rem % 3600) // 60), int(rem % 60)
        icon = "🔴" if pct < 0.25 else ("🟠" if pct < 0.5 else "🟢")
        st.progress(pct)
        st.markdown(f'{icon} **SLA {h:02d}:{m:02d}:{s:02d}** remaining · `{inc["id"]}` · {inc["priority"]}')
    if hasattr(st, "fragment"):
        st.fragment(run_every=1)(render)()
    else:
        render()


def _live_feed():
    def render():
        realtime.tick()
        viz.feed(realtime.recent(14))
    if hasattr(st, "fragment"):
        st.fragment(run_every=3)(render)()
    else:  # older Streamlit: manual refresh
        if st.button("↻ Refresh feed"):
            st.rerun()
        render()


def render(name, role):
    sv, ed, it_inc, ch, me, G = E.load()
    it = dict(services=sv, edges=ed, incidents=it_inc, changes=ch, metrics=me,
              tickets=E.load_tickets(), kpis=E.load_kpis(), G=G)
    ddata = DE.load()

    it_open = [i for i in it_inc if i["status"] == "open"]
    dop_open = [i for i in ddata["incidents"] if i["status"] == "open"]
    at_risk = 0
    for i in it_open + dop_open:
        _, hrs = _sla(i)
        if hrs is not None and hrs < SLA_HOURS.get(i["priority"], 8) * 0.5:
            at_risk += 1

    st.subheader("Live Operations — real-time monitoring")
    st.caption("Cross-domain event stream · collaboration · delegation. Simulated stream, shared state.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open incidents", len(it_open) + len(dop_open))
    m2.metric("SLA at risk", at_risk)
    m3.metric("Events (last 15 min)", realtime.events_last_15min())
    m4.metric("Collaborators", len(collab.collaborators()))

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### 📡 Live event stream")
        _live_feed()
        st.markdown("#### 🗂️ Incident queue (IT Ops + DataOps)")
        rows = [{"ref": i["id"], "domain": "IT Ops", "title": i["title"],
                 "priority": i["priority"], "owner": i["owner_team"]} for i in it_open]
        rows += [{"ref": i["id"], "domain": "DataOps", "title": i["title"],
                  "priority": i["priority"], "owner": i["owner_team"]} for i in dop_open]
        viz.queue_cards(rows)

    with right:
        refs = [r["ref"] for r in rows]
        if refs:
            ref = st.selectbox("Focus incident", refs, key="lo_focus")
            st.markdown("#### ⏱️ Live SLA countdown")
            _sla_countdown(ref, it, ddata)

            st.markdown("#### 🔔 Notifications")
            unread = collab.unread_count(role)
            if unread:
                st.caption(f'**{unread} unread** for {role}')
            notes = collab.notifications_for(role)
            if notes:
                for n in notes:
                    mark = "•" if n["read"] else "🔵"
                    st.markdown(f'{mark} `{n["ts"][11:]}` {n["text"]} · _{n["ref_id"]}_')
                if st.button("Mark all read", key="lo_read"):
                    collab.mark_all_read(role)
                    st.rerun()
            else:
                st.caption("No notifications.")

            st.markdown("#### 👥 Collaboration")
            for c in collab.comments(ref):
                st.markdown(f'**{c["author"]}** · _{c["role"]}_ · `{c["ts"][11:]}`  \n{c["text"]}')
            msg = st.text_area("Add an update  (mention: @DataEngineer @DataOwner @PlatformEngineer "
                               "@IncidentManager @L2 @Developer @CSM @DBA)", key="lo_msg")
            if st.button("Post update", type="primary", key="lo_post"):
                collab.add_comment(ref, f'{name} ({role})', role, msg)
                for m_role in collab.parse_mentions(msg):
                    collab.add_notification(m_role, ref, f'{name} ({role}) mentioned you: “{msg.strip()[:70]}”')
                st.session_state["flash"] = ("Update posted" +
                                             (f' — notified {", ".join(collab.parse_mentions(msg))}.'
                                              if collab.parse_mentions(msg) else "."))
                st.rerun()

            st.markdown("#### 🔀 Delegate a specific action")
            rec = _rec(ref, it, ddata)
            to = st.selectbox("Delegate to", TEAMS, key="lo_to")
            action = st.text_input("Action", value=rec["action"], key="lo_action")
            if st.button("Delegate (assign)", key="lo_delegate"):
                collab.add_delegation(ref, role, to, action)
                collab.add_notification(to, ref, f'{role} delegated to you: “{action}”')
                st.session_state["flash"] = f'Delegated to **{to}**: “{action}” — they’ve been notified.'
                st.rerun()
            for d in collab.delegations(ref):
                col1, col2 = st.columns([3, 1])
                col1.markdown(f'**{d["frm"]} → {d["to_"]}** · {d["action"]}  \n'
                              f'_status: {d["status"]} · `{d["ts"][11:]}`_')
                if d["status"] == "assigned" and col2.button("Accept", key=f'acc_{d["id"]}'):
                    collab.set_delegation_status(d["id"], "accepted")
                    st.rerun()
                elif d["status"] == "accepted" and col2.button("Done", key=f'done_{d["id"]}'):
                    collab.set_delegation_status(d["id"], "done")
                    st.rerun()

            corr = journey.correlation_for(ref)
            if corr:
                st.markdown("#### 🔗 Cross-domain")
                st.info(f'Linked to **{corr["other_domain"]} {corr["other_id"]}** — shared cause '
                        f'**{corr["shared_cause"]}**.')
