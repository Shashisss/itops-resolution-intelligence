#!/usr/bin/env python3
"""Shared journey layer — detection, time-correlated timeline, ranked hypotheses,
INDEPENDENT verification, resolution record and cross-domain correlation.
Used by both the IT Ops and DataOps domains."""
import sqlite3
import datetime as dt
import json
import pandas as pd
import streamlit as st
import viz

DB = "data/ops.db"
CONF_RANK = {"high": 3, "medium": 2, "low": 1}
KIND_ICON = {"change": "🔧", "alert": "🚨", "incident": "📟", "ticket": "🎫", "impact": "📉",
             "repair": "🛠", "verify": "✅", "detect": "🔎"}

# ------------------------------------------------------------------ ONE shared lifecycle
# The single progress model used across IT Ops and DataOps (see viz.thread_spine).
LIFECYCLE = ["Detect", "Correlate", "Coordinate", "Act", "Verify", "Close"]
# The nav target that opens an incident workspace (kept here so shell/app/callbacks agree).
WORKSPACE_NAV = "Incidents"

_IT_STAGE_TO_THREAD = {"Detected": "Detect", "Triaged": "Correlate", "Diagnosed": "Correlate",
                       "Change raised": "Coordinate", "Fix in progress": "Act",
                       "Fix applied": "Verify", "Verified": "Verify", "Closed": "Close"}
_DOP_STAGE_TO_THREAD = {"Detected": "Detect", "Triaged": "Correlate", "Diagnosed": "Correlate",
                        "Fix in progress": "Act", "Fix applied": "Verify",
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


# ---------------------------------------------------------------- cross-domain thread edges
# Relationships are STRUCTURED records (not built in UI code). kind distinguishes an observed
# signal/relationship from an inferred hypothesis; confidence is a rule-based indicator.
_DEFAULT_THREAD_EDGES = [
    ("TE-1", "INC-8841", "Schema change (core_ledger)", "Pipeline failure (payments_bronze_ingest)",
     "caused", "observed", "DataOps · run R-9001 SCHEMA_MISMATCH", 60, "high"),
    ("TE-2", "INC-8841", "Pipeline failure", "payments_gold stale",
     "→ stale data", "observed", "DataOps · freshness 45m > 15m SLA", 45, "high"),
    ("TE-3", "INC-8841", "payments_gold stale", "Payment API degradation",
     "→ impacts", "inferred", "IT Ops · data_age 45>15 with error_rate 8.1>1 (to validate)", 44, "medium"),
    ("TE-4", "INC-8841", "DB connection saturation", "Payment API degradation",
     "contributes", "inferred", "IT Ops · active_connections 720>700 (secondary cause)", 43, "low"),
]


def _ensure_thread_edges():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS thread_edges(id TEXT PRIMARY KEY, thread_ref TEXT, src TEXT, "
                "dst TEXT, rel TEXT, kind TEXT, source TEXT, ts TEXT, confidence TEXT)")
    n = con.execute("SELECT COUNT(*) FROM thread_edges").fetchone()[0]
    if n == 0:
        base = dt.datetime.now().replace(second=0, microsecond=0)
        rows = [(i, tr, s, d, rel, k, src, (base - dt.timedelta(minutes=off)).strftime("%H:%M"), conf)
                for (i, tr, s, d, rel, k, src, off, conf) in _DEFAULT_THREAD_EDGES]
        con.executemany("INSERT INTO thread_edges VALUES(?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


def thread_edges_for(ref_id):
    """Return the structured cross-domain relationships for an incident's thread."""
    _ensure_thread_edges()
    c = correlation_for(ref_id)
    thread_ref = c["it_id"] if c else ref_id
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM thread_edges WHERE thread_ref=? ORDER BY id", (thread_ref,))]
    con.close()
    return rows


def _nav_to(value):
    """on_click callback — navigate the top menu to another destination."""
    st.session_state["nav"] = value


# ---------------------------------------------------------------- collaboration stats
def collab_stats(inc):
    """Measured collaboration around an incident (from real comment/delegation records)."""
    import collab
    cs = collab.comments(inc["id"])
    ds = collab.delegations(inc["id"])
    participants = sorted({c["author"] for c in cs if c["author"] != "Recommendation engine"})
    done = sum(1 for d in ds if d["status"] == "done")
    first_ts = ds[-1]["ts"] if ds else None
    coord_min = None
    if first_ts:
        try:
            coord_min = int((dt.datetime.fromisoformat(first_ts)
                             - dt.datetime.fromisoformat(inc["created_at"])).total_seconds() / 60)
        except Exception:
            coord_min = None
    return {"participants": participants, "handoffs": len(ds), "handoffs_done": done,
            "coord_min": coord_min, "updates": len(cs)}


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
    """Board-facing verdict for an incident — the PERSISTED record is authoritative.

    Order: persisted resolution record → closed incident (Verified, since closure only happens on an
    independently verified recovery) → session verdict → Investigating."""
    rec = resolution_record(inc["id"])
    if rec and rec.get("verdict"):
        return rec["verdict"]
    if (inc.get("status") or "").lower() == "closed":
        return "Verified"
    return st.session_state.get(f'verdict_{inc["id"]}', "Investigating")


# ---------------------------------------------------------------- authoritative resolution state
def _ensure_resolution_table():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS resolution_state("
                "ref_id TEXT PRIMARY KEY, verdict TEXT, action_id TEXT, actor TEXT, "
                "closed_at TEXT, updated_at TEXT, checks TEXT)")
    con.commit()
    con.close()


def set_resolution(ref_id, verdict, action_id=None, actor="Verification service", checks=None):
    """Persist the authoritative resolution record (verdict, action, checks, actor, closure time)."""
    _ensure_resolution_table()
    now = dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    closed = now if verdict == "Verified" else None
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO resolution_state(ref_id,verdict,action_id,actor,closed_at,updated_at,checks) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(ref_id) DO UPDATE SET "
        "verdict=excluded.verdict, action_id=excluded.action_id, actor=excluded.actor, "
        "closed_at=excluded.closed_at, updated_at=excluded.updated_at, checks=excluded.checks",
        (ref_id, verdict, action_id, actor, closed, now, json.dumps(checks) if checks else None))
    con.commit()
    con.close()


def resolution_record(ref_id):
    _ensure_resolution_table()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM resolution_state WHERE ref_id=?", (ref_id,)).fetchone()
    con.close()
    if not r:
        return None
    d = dict(r)
    if d.get("checks"):
        try:
            d["checks"] = json.loads(d["checks"])
        except Exception:
            d["checks"] = None
    return d


def current_verdict(inc):
    """The verdict every view must agree on: persisted record first, then session."""
    rec = resolution_record(inc["id"])
    if rec and rec.get("verdict"):
        return rec["verdict"]
    return st.session_state.get(f'verdict_{inc["id"]}', "Investigating")


def applied_action(inc_id):
    rec = resolution_record(inc_id)
    if rec and rec.get("action_id"):
        return rec["action_id"]
    return st.session_state.get(f'it_opt_applied_{inc_id}') or \
        st.session_state.get(f'dop_opt_applied_{inc_id}')


def render_recovery_by_verdict(title, verdict, restored, partial, failed):
    """Conditional recovery message — the SAME rule everywhere. Only Verified may say restored;
    Mitigated must say partial; Recovery failed must say failed."""
    if verdict == "Verified":
        render_recovery_update(title, restored + " (Simulated.)")
    elif verdict == "Mitigated":
        render_recovery_update(title, partial + " (Simulated.)", kind="warning")
    elif verdict == "Recovery failed":
        render_recovery_update(title, failed + " (Simulated.)", kind="error")


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
    return (f'Ranked by evidence strength — **{t["confidence"]}** confidence on *{t["type"]}*. Confidence is a '
            f'**rule-based indicator** computed from observed signals (recency, magnitude vs threshold, '
            f'correlation with an open incident), not a calibrated model score.')


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
