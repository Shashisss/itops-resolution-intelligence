#!/usr/bin/env python3
"""Shared journey layer — detection, time-correlated timeline, ranked hypotheses,
INDEPENDENT verification, resolution record and cross-domain correlation.
Used by both the IT Ops and DataOps domains."""
import sqlite3
import datetime as dt
import pandas as pd
import streamlit as st
import viz

DB = "data/ops.db"
CONF_RANK = {"high": 3, "medium": 2, "low": 1}
KIND_ICON = {"change": "🔧", "alert": "🚨", "incident": "📟", "ticket": "🎫", "impact": "📉",
             "repair": "🛠", "verify": "✅", "detect": "🔎"}

# ------------------------------------------------------------------ ONE shared lifecycle
# The single progress model used across IT Ops and DataOps (see viz.thread_spine).
LIFECYCLE = ["Detect", "Correlate", "Coordinate", "Verify", "Close"]
# The nav target that opens an incident workspace (kept here so shell/app/callbacks agree).
WORKSPACE_NAV = "Incidents & resolution threads"

_IT_STAGE_TO_THREAD = {"Detected": "Detect", "Triaged": "Correlate", "Diagnosed": "Correlate",
                       "Change raised": "Coordinate", "Fix in progress": "Coordinate",
                       "Fix applied": "Verify", "Verified": "Verify", "Closed": "Close"}
_DOP_STAGE_TO_THREAD = {"Detected": "Detect", "Triaged": "Correlate", "Diagnosed": "Correlate",
                        "Fix in progress": "Coordinate", "Fix applied": "Verify",
                        "Backfilled": "Verify", "Validated": "Verify", "Closed": "Close"}


def lifecycle_stage(inc):
    """Map a stored (IT or DataOps) stage value onto the ONE shared lifecycle vocabulary."""
    s = inc.get("stage") or ""
    return _IT_STAGE_TO_THREAD.get(s) or _DOP_STAGE_TO_THREAD.get(s) or "Detect"


def timeline(ref_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM timeline WHERE ref_id=? ORDER BY ts", (ref_id,))]
    con.close()
    return rows


def timeline_multi(refs):
    """One canonical history, merged across refs (cross-domain threads)."""
    rows = []
    for r in refs:
        rows += timeline(r)
    return sorted(rows, key=lambda x: x.get("ts", ""))


def add_event(ref_id, domain, kind, detail):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO timeline VALUES(?,?,?,?,?,?)",
                (f'E-{dt.datetime.now().strftime("%H%M%S%f")}', ref_id, domain,
                 dt.datetime.now().replace(second=0, microsecond=0).isoformat(timespec="minutes"), kind, detail))
    con.commit()
    con.close()


def correlation_for(ref_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM correlations WHERE it_id=? OR dop_id=?", (ref_id, ref_id)).fetchone()
    con.close()
    if not r:
        return None
    d = dict(r)
    if d["it_id"] == ref_id:
        d["other_id"], d["other_domain"] = d["dop_id"], "DataOps"
    else:
        d["other_id"], d["other_domain"] = d["it_id"], "IT Ops"
    return d


def verdict(rows, applied):
    """Overall recovery verdict from independently-checked rows."""
    if not applied or not rows:
        return "Investigating"
    oks = [str(r["result"]).startswith("✅") for r in rows]
    if all(oks):
        return "Verified"
    if any(oks):
        return "Mitigated"
    return "Recovery failed"


def display_verdict(inc):
    """Board-facing verdict for an incident.

    Closure only happens on an independently verified recovery, so a closed incident is Verified.
    An open incident uses the session's live verdict (set when remediation is applied) and defaults
    to Investigating. NOTE: session verdicts are not persisted, so they reset to Investigating on
    restart/reboot — the board labels this honestly."""
    if (inc.get("status") or "").lower() == "closed":
        return "Verified"
    return st.session_state.get(f'verdict_{inc["id"]}', "Investigating")


def render_verdict(state):
    viz.verdict_badge(state)


def rank(hyps):
    # root-cause data dependency ranks first, then confirmed, then confidence
    return sorted(hyps, key=lambda h: (h["type"] == "upstream data", h["status"] == "confirmed",
                                       CONF_RANK.get(h["confidence"], 0)), reverse=True)


def confidence_note(hyps):
    if not hyps:
        return ""
    t = hyps[0]
    return (f'Ranked by evidence strength — **{t["confidence"]}** confidence on *{t["type"]}*. Confidence is '
            f'calibrated from observed signals (recency, magnitude vs threshold, correlation with an open incident), '
            f'not from a model.')


# ------------------------------------------------------------------ render helpers
def render_detection(inc_id, verifier):
    alerts = [r for r in timeline(inc_id) if r["kind"] in ("alert", "detect")]
    st.markdown("**Detection — what fired and when**")
    if alerts:
        for a in alerts:
            st.write(f'- `{a["ts"]}` · 🚨 {a["detail"]}')
    else:
        st.caption("No alert records.")
    st.caption(f'Detection verified by: **{verifier}** (rule-based signals, not model output).')


def render_timeline(inc_id):
    st.markdown("**Operational timeline (time-correlated across systems)**")
    viz.timeline(timeline(inc_id))


def render_hypotheses(hyps, title="Root cause — ranked hypotheses (suspected vs confirmed)"):
    hyps = rank(hyps)
    st.markdown(f"**{title}**")
    if not hyps:
        st.info("No signal linked yet.")
        return hyps
    viz.hypothesis_cards(hyps)
    st.caption(confidence_note(hyps))
    return hyps


def render_verification(rows, verifier):
    st.markdown("**Verification — independent (not the operator's claim)**")
    st.caption(f'Re-checked by **{verifier}** from raw telemetry against thresholds, independently of who applied '
               f'the repair.')
    st.dataframe(pd.DataFrame(rows), hide_index=True)


def render_resolution(inc_id, applied, sla_txt, owner, verdict="", extra=""):
    """Only CLOSE when verification says Verified. Mitigated/Failed stay OPEN."""
    if not applied:
        return
    st.markdown("**Resolution record**")
    if verdict == "Verified":
        st.success(f'Incident **{inc_id}** independently **verified and closed** · SLA outcome: **{sla_txt}** '
                   f'· owner: {owner}.')
        st.markdown(f'**Learning:** evidence captured → runbook / known-error updated.{(" " + extra) if extra else ""}')
    elif verdict == "Mitigated":
        st.warning(f'Fix applied but **NOT verified** — incident **{inc_id}** remains **OPEN** · SLA {sla_txt} · '
                   f'owner {owner}. Partial recovery only — further action required.')
    elif verdict == "Recovery failed":
        st.error(f'Recovery **FAILED** — incident **{inc_id}** remains **OPEN** · SLA {sla_txt} · owner {owner}. '
                 f'Escalate.')
    else:
        st.info(f'Incident **{inc_id}** — status: {verdict or "investigating"} (not closed).')


_STATUS_COLOR = {"assigned": "#d97706", "accepted": "#0891b2", "done": "#16a34a"}


def actors(rec):
    import re as _re
    return [a.strip() for a in _re.split(r"\s*\+\s*|,\s*", rec.get("actor", "")) if a.strip()]


def engage_block(ref, action, actors_list):
    """Two-tier autonomy: COORDINATION is autonomous under policy (delegate + notify + log);
    the change itself stays human-gated below."""
    import collab
    auto = st.session_state.get("auto_coord", False)
    delegs = collab.delegations(ref)
    if auto and not delegs and actors_list:
        _engage(ref, action, tuple(actors_list), auto=True)   # autonomous coordination
        delegs = collab.delegations(ref)
    st.markdown('<span class="ri-tag" style="background:#16a34a">🟢 Coordination — autonomous under '
                'policy</span> <span style="color:#64748b;font-size:12px">(assign + notify carries no '
                'production risk)</span>', unsafe_allow_html=True)
    if delegs:
        st.markdown("**🤝 Collaboration status**")
        for d in delegs:
            col = _STATUS_COLOR.get(d["status"], "#64748b")
            st.markdown(f'<div class="ri-ev-chip" style="border-left-color:{col}"><b>{d["frm"]} → '
                        f'{d["to_"]}</b> · {d["action"]} · <span class="ri-tag" style="background:{col}">'
                        f'{d["status"]}</span></div>', unsafe_allow_html=True)
    if auto:
        st.caption("🤖 Auto-coordinate is ON — the agent engaged the next actor automatically under policy. "
                   "The production change below still requires approval.")
    else:
        st.button("🤝 Coordinate — delegate & notify", key="engage_" + ref,
                  type=("secondary" if delegs else "primary"),
                  on_click=_engage, args=(ref, action, tuple(actors_list)))


def _engage(ref, action, actors_list, auto=False):
    import collab
    for a in actors_list:
        collab.add_delegation(ref, "Recommendation engine", a, action)
        collab.add_notification(collab.ACTOR_TO_ROLE.get(a, a), ref,
                                f'Action delegated to {a}: “{action}”')
    who = "Auto-coordinated under policy (coordination · low risk)" if auto else "Coordinated"
    collab.add_comment(ref, "Recommendation engine", "System",
                       f'{who}: engaged {", ".join(actors_list)} — {action}')
    st.session_state["flash"] = (f'{"Auto-coordinated" if auto else "Coordinated"} — **'
                                 f'{", ".join(actors_list)}** assigned and notified. Acceptance and completion '
                                 f'are tracked on the incident; the production change still needs approval.')


def render_recovery_update(title, body, kind="success"):
    st.markdown(f"**{title}**"
                + ("" if kind == "success" else " — *not a closure*"))
    {"success": st.success, "warning": st.warning, "error": st.error}[kind](body)


def _nav(key, steps, delta):
    """on_click callback for wizard Back/Next (runs before widgets are instantiated)."""
    cur = st.session_state.get(key, steps[0])
    i = steps.index(cur) if cur in steps else 0
    st.session_state[key] = steps[max(0, min(len(steps) - 1, i + delta))]


def wizard(key, steps, renderers, default=0, help=None, handoffs=None):
    """Single-step-at-a-time wizard with one progress metaphor and a handshake into each stage."""
    if key not in st.session_state or st.session_state.get(key) not in steps:
        st.session_state[key] = steps[default]
    st.radio("Step", steps, horizontal=True, key=key)
    step = st.session_state[key]
    viz.resolution_flow(current=step)
    if handoffs and step in handoffs:
        viz.handshake(handoffs[step])          # the handshake BEFORE this stage's content
    if help and step in help:
        st.markdown(f'<div class="ri-card" style="background:#f8fafc;padding:9px 13px;margin:2px 0 10px">'
                    f'<b>What this stage is:</b> {help[step]}</div>', unsafe_allow_html=True)
    renderers[step]()
    i = steps.index(step)
    back, nxt, _ = st.columns([1, 1, 5])
    back.button("← Back", key=key + "_back", disabled=(i == 0),
                on_click=_nav, args=(key, steps, -1))
    nxt.button("Next →", key=key + "_next", type="primary", disabled=(i == len(steps) - 1),
               on_click=_nav, args=(key, steps, +1))


def _goto(domain, inc_key, ref):
    """on_click callback — opens an incident's workspace (search, cross-domain links, board cards).
    Runs before widgets are instantiated, so setting widget/session keys is allowed."""
    st.session_state["nav"] = WORKSPACE_NAV
    st.session_state["open_incident"] = {"domain": domain, "ref": ref}


def render_correlation(inc_id):
    c = correlation_for(inc_id)
    if not c:
        return
    st.markdown("**Cross-domain correlation**")
    st.info(f'🔗 Shared root cause **{c["shared_cause"]}** links this to **{c["other_domain"]} '
            f'{c["other_id"]}**. {c["note"]}')
    viz.chain([c["dop_id"], "biz", c["it_id"]],
              {c["dop_id"]: f'DataOps {c["dop_id"]}', "biz": "Business service · Payments",
               c["it_id"]: f'IT Ops {c["it_id"]}'},
              stale=(c["dop_id"], c["it_id"]), highlight=("biz",))
    if c["other_domain"] == "DataOps":
        st.button(f'View {c["other_id"]} in DataOps →', key="go_dop_" + inc_id,
                  on_click=_goto, args=("DataOps", None, c["other_id"]))
    else:
        st.button(f'View {c["other_id"]} in IT Ops →', key="go_it_" + inc_id,
                  on_click=_goto, args=("IT Ops", None, c["other_id"]))
