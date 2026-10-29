#!/usr/bin/env python3
"""Collapsed-section summaries — the one line a closed section must still say.

An accordion that hides a critical fact is a worse page than a long one. Every collapsed header
therefore carries: the stage name, its state, its clock against the stage OLA, and the single most
important fact from inside it. A blocked close, an unverified recovery or an overdue request is
stated *in the header*, not only after the click.

All numbers come from the record (timeline anchors, stage OLAs, delegations, verdict, closure gate),
never from prose.
"""
import datetime as dt

import streamlit as st

import analytics
import collab
import journey
import learn
import story
import viz

STAGE_ORDER = journey.LIFECYCLE


def _olas():
    """Stage → target minutes. The table is authoritative; the defaults keep an un-migrated
    database usable."""
    try:
        # read, never seed: engine.load_stage_olas() inserts rows, and a render must not mutate.
        rows = story._rows("SELECT stage, target_min FROM stage_olas")
        got = {r["stage"]: r["target_min"] for r in rows if r.get("stage")}
        return {**analytics.STAGE_OLA_DEFAULT, **got}
    except Exception:
        return dict(analytics.STAGE_OLA_DEFAULT)


def _anchors(inc):
    try:
        rec = journey.resolution_record(inc["id"]) or {}
        return analytics._stage_anchors(inc["id"], rec.get("closed_at"))
    except Exception:
        return []


def _durations(anchors, now):
    """Minutes between consecutive stage anchors; the current stage runs to now."""
    out = {}
    for i, (stage, ts) in enumerate(anchors):
        start = analytics._ts(ts)
        if start is None:
            continue
        end = analytics._ts(anchors[i + 1][1]) if i + 1 < len(anchors) else now
        if end is not None and end >= start:
            out[stage] = int((end - start).total_seconds() / 60)
    return out


def _hhmm(ts):
    try:
        return dt.datetime.fromisoformat(str(ts)).strftime("%H:%M")
    except Exception:
        return "—"


def _leads(inc):
    try:
        import agents
        return agents.facts(inc)["leads"]
    except Exception:
        return {"reviewed": 0, "ranked": 0, "rejected": 0}


def _recommendation(inc):
    try:
        if inc["id"].startswith("DOP"):
            import dataops_engine as DE
            rec = DE.recommend(inc, DE.causes(inc, DE.load()), DE.load())
            return rec.get("action"), rec.get("mode")
        import engine as E
        services, edges, incidents, changes, metrics, G = E.load()
        rec = E.recommend(inc, E.causes(inc, G, changes, metrics, services))
        return rec.get("action"), rec.get("mode")
    except Exception:
        return None, None


def stage_rows(inc, now=None):
    """One row per lifecycle stage: state, clock, OLA and the fact that matters most."""
    now = now or story._now()
    current = journey.lifecycle_stage(inc)
    idx_cur = STAGE_ORDER.index(current) if current in STAGE_ORDER else 0
    olas = _olas()
    durations = _durations(_anchors(inc), now)
    leads = _leads(inc)
    corr = journey.correlation_for(inc["id"])
    sig = story._rows("SELECT kind, confidence, src, dst FROM thread_edges WHERE thread_ref=? "
                      "ORDER BY CASE kind WHEN 'inferred' THEN 0 ELSE 1 END, "
                      "CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END LIMIT 1",
                      (inc["id"],))
    score = None
    if sig:
        import agents
        score = agents.SIGNAL_SCORE.get((sig[0]["kind"] or "").lower(), {}).get(
            (sig[0]["confidence"] or "").lower())
    verdict = journey.current_verdict(inc)
    gate = journey.closure_state(inc)
    asks = [d for d in collab.delegations(inc["id"]) if d.get("status") != "done"]
    overdue = [d for d in asks if collab.is_overdue(d)]
    action, mode = _recommendation(inc)
    rec = learn.get(inc["id"])
    alerts = story._rows("SELECT ts FROM timeline WHERE ref_id=? AND kind IN ('alert','change') "
                         "ORDER BY ts", (inc["id"],))

    rows = []
    for i, stage in enumerate(STAGE_ORDER):
        state = "done" if i < idx_cur else ("current" if i == idx_cur else "todo")
        badge, tone, fact = "", "", ""
        if stage == "Detect":
            fact = f'{len(alerts)} signal(s) · first {_hhmm(alerts[0]["ts"]) if alerts else "—"}'
        elif stage == "Triage":
            fact = f'owner {inc.get("owner_team") or "unassigned"}'
        elif stage == "Investigate":
            fact = f'{leads["ranked"]} lead(s) ranked · {leads["reviewed"]} signal(s) reviewed'
        elif stage == "Correlate":
            if corr:
                fact = f'{corr["other_id"]} linked · {score:.2f} inferred' if score is not None \
                    else f'{corr["other_id"]} linked'
            else:
                fact = "no upstream link recorded"
        elif stage == "Act":
            if overdue:
                badge, tone = "OVERDUE", "#b91c1c"
                fact = f'{len(overdue)} request(s) past deadline'
            else:
                fact = f'{action} · {mode}' if action else "no action applied yet"
        elif stage == "Verify":
            if verdict and verdict != "Verified" and inc.get("status") != "closed":
                badge, tone = "UNVERIFIED", "#b45309"
            fact = f'verdict {verdict}'
        elif stage == "Close":
            if gate.get("closed"):
                fact = "closed on the verified record"
            elif gate.get("eligible"):
                badge, tone, fact = "READY", "#166534", "eligible · no open request"
            else:
                badge, tone = "BLOCKED", "#b91c1c"
                reason = (gate.get("reasons") or ["requirement open"])[0]
                fact = reason if len(reason) <= 58 else reason[:55].rstrip() + "…"
        elif stage == "Learn":
            fact = f'record saved {rec.get("saved_at", "")[:16]}' if rec else "not captured yet"

        ola = olas.get(stage)
        dur = durations.get(stage)
        clock = ""
        if dur is not None:
            clock = f'{dur}m / {ola}m OLA' if ola else f'{dur}m'
        elif ola:
            clock = f'{ola}m OLA'
        if state == "current" and ola and dur is None:
            clock = f'{ola}m OLA target'
        rows.append({"stage": stage, "state": state, "badge": badge, "tone": tone,
                     "clock": clock, "fact": fact})
    return rows


def extra_rows(inc, dom):
    """The non-stage sections that fold away: connections, evidence carried, activity."""
    ref = inc["id"]
    try:
        import graph, graph_views
        rows = graph.store().neighbours(graph.incident_node_id(ref))
        n_conn = len(rows)
        obs = sum(1 for r in rows if r["edge"].get("basis") == "observed")
    except Exception:
        n_conn, obs = 0, 0
    ev = story.evidence(inc, limit=99)
    acts = story._rows("SELECT id FROM comments WHERE ref_id=? UNION ALL "
                       "SELECT id FROM timeline WHERE ref_id=?", (ref, ref))
    try:
        import agents
        ap = agents.panel(inc)
    except Exception:
        ap = None
    if ap:
        sig = ap["specialist"]["signal"]
        agent_line = (f'{ap["specialist"]["agent"]} · {ap["specialist"]["reviewed"]} signals · '
                      f'{sig["score"]:.2f} {sig["basis"]}' if sig.get("score") is not None
                      else f'{ap["specialist"]["agent"]} · {ap["specialist"]["reviewed"]} signals')
        agent_fact = f'{agent_line} · rung {ap["rung"]}'
    else:
        agent_fact = "no agent definition for this incident"
    return [
        {"key": "agents", "title": "Who's on it · SIMULATED", "fact": agent_fact,
         "clock": "", "badge": "", "tone": ""},
        {"key": "connections", "title": "Connections",
         "fact": (f'{n_conn} connections · {obs} observed · {n_conn - obs} inferred'
                  if n_conn else "no connections recorded"),
         "clock": "", "badge": "", "tone": ""},
        {"key": "evidence", "title": "Evidence carried over",
         "fact": f'{len(ev)} item(s) travel with the thread', "clock": "", "badge": "", "tone": ""},
        {"key": "activity", "title": "Activity & audit",
         "fact": f'{len(acts)} event(s) on the record', "clock": "", "badge": "", "tone": ""},
        {"key": "record", "title": "Record, sources & assumptions",
         "fact": "how this screen is computed", "clock": "", "badge": "", "tone": ""},
    ]


# ------------------------------------------------------------------ accordion plumbing
def init_open(inc):
    """Default: the current stage is open and everything else is closed."""
    ref = inc["id"]
    if f"open_{ref}" not in st.session_state:
        st.session_state[f"open_{ref}"] = f"stage:{journey.lifecycle_stage(inc)}"
    return st.session_state[f"open_{ref}"]


def accordion_stages(inc, stage_fns, step_help, handoffs, prefix):
    """Render the lifecycle as an accordion: the open stage only, every other header stating its own
    state, clock and most important fact."""
    ref = inc["id"]
    opened = init_open(inc)
    with st.container(key=f"acc_group_{ref}_stages"):
        _stage_list(inc, stage_fns, step_help, handoffs, prefix, opened)


def _stage_list(inc, stage_fns, step_help, handoffs, prefix, opened):
    """Current stage first (it is the open one), then the rest in lifecycle order — so what is open
    is on screen without scrolling past everything that precedes it."""
    ref = inc["id"]
    rows = stage_rows(inc)
    current = journey.lifecycle_stage(inc)
    rows.sort(key=lambda r: (r["stage"] != current, STAGE_ORDER.index(r["stage"])))
    for row in rows:
        stage = row["stage"]
        key = f"stage:{stage}"
        detail = " · ".join(b for b in (row["clock"], row["fact"]) if b)
        with st.container(key=f"{prefix}_{ref}_anchor_{stage}"):
            viz.accordion_header(ref, key, stage, detail=detail, badge=row["badge"],
                                 is_open=(opened == key))
            if opened == key:
                if step_help.get(stage):
                    st.caption(step_help[stage])
                if handoffs.get(stage):
                    viz.handshake(handoffs[stage])
                stage_fns[stage]()


def record_body(inc, dom):
    """What is behind this screen: the source records, the assumptions, and the joins."""
    st.markdown(f'**Primary record** — {inc["id"]} · {inc.get("priority")} · '
                f'owner {inc.get("owner_team") or "—"} · status {inc.get("status")}')
    tk = story._rows("SELECT id, status, assignee FROM tickets WHERE incident_id=?", (inc["id"],))
    if tk:
        st.markdown(f'**Jira defect** — {tk[0]["id"]} ({tk[0]["status"]}) · {tk[0]["assignee"]}')
    st.caption("Sources: ServiceNow · Jira · Observability · CMDB · dop_freshness")
    st.caption("SLA — " + _sla_assumption())
    st.caption("Every relative time uses one clock per render (runclock), so two panels cannot "
               "disagree by a minute.")


def _sla_assumption():
    try:
        import personas
        return personas.SLA_ASSUMPTION
    except Exception:
        return "priority-based estimate; no pause rules or business calendars."
