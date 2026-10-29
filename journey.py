#!/usr/bin/env python3
"""Shared journey layer — detection, time-correlated timeline, ranked hypotheses,
INDEPENDENT verification, resolution record and cross-domain correlation.
Used by both the IT Ops and DataOps domains."""
import os
import sqlite3
import datetime as dt
import json
import pandas as pd
import streamlit as st
import viz

DB = os.environ.get("RI_DB", "data/ops.db")
CONF_RANK = {"high": 3, "medium": 2, "low": 1}

# ------------------------------------------------------------------ ONE shared lifecycle
# The single progress model used across IT Ops and DataOps (see viz.thread_spine). Learn is the
# stage after Close: a closed incident is not finished until what worked is captured.
LIFECYCLE = ["Detect", "Triage", "Investigate", "Correlate", "Act", "Verify", "Close", "Learn"]
# The nav target that opens an incident workspace (kept here so shell/app/callbacks agree).
WORKSPACE_NAV = "Incident"

# The four phases the stepper shows (v99). The eight stages below are what the data records.
PHASES = viz.PHASES
phase_of = viz.phase_of
stages_in_phase = viz.stages_in_phase

_IT_STAGE_TO_THREAD = {"Detected": "Detect", "Triaged": "Triage", "Diagnosed": "Correlate",
                       "Change raised": "Act", "Fix in progress": "Act",
                       "Fix applied": "Verify", "Verified": "Verify", "Closed": "Close",
                       "Learned": "Learn"}
_DOP_STAGE_TO_THREAD = {"Detected": "Detect", "Triaged": "Triage", "Diagnosed": "Correlate",
                        "Fix in progress": "Act", "Fix applied": "Verify",
                        "Backfilled": "Verify", "Validated": "Verify", "Closed": "Close",
                        "Learned": "Learn"}


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


# ---------------------------------------------------------------- one definition of staleness
def freshness(dataset_id):
    """The ONE definition of staleness: now − dop_freshness.last_updated.

    The thread edge, the hypothesis evidence, the metric card and the verification row all render
    this number. A hardcoded "45m" in a seed string cannot agree with a value computed later, so
    every live claim is rewritten from the stored freshness record at render time."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT f.last_updated, f.sla_min, d.name FROM dop_freshness f "
                    "LEFT JOIN dop_datasets d ON d.id=f.dataset_id WHERE f.dataset_id=?",
                    (dataset_id,)).fetchone()
    con.close()
    if not r:
        return None
    try:
        lag = int((dt.datetime.now() - dt.datetime.fromisoformat(r["last_updated"])).total_seconds() / 60)
    except Exception:
        return None
    return {"dataset_id": dataset_id, "name": r["name"] or dataset_id, "lag_min": lag,
            "sla_min": r["sla_min"], "breach": lag > r["sla_min"]}


def stale_dataset(ref):
    """The dataset an IT incident consumes — the one whose staleness the thread is talking about."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT dataset_id FROM service_data WHERE service_id="
                    "(SELECT service_id FROM incidents WHERE id=?)", (ref,)).fetchone()
    con.close()
    return r["dataset_id"] if r else None


def _stale_text(text, ds):
    """Rewrite a stored staleness claim with the computed value — one number, both places."""
    import re
    f = freshness(ds) if ds else None
    if not f:
        return text
    text = re.sub(r"freshness \d+m", f'freshness {f["lag_min"]}m', text)
    text = re.sub(r"data_age(_min)? \d+", lambda m: f'{m.group(0).rsplit(" ", 1)[0]} {f["lag_min"]}', text)
    return text


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
    """Return the structured cross-domain relationships for an incident's thread.

    Staleness claims are rewritten from the stored freshness record so the thread and the
    investigation can never disagree about the same number."""
    _ensure_thread_edges()
    c = correlation_for(ref_id)
    thread_ref = c["it_id"] if c else ref_id
    ds = stale_dataset(thread_ref)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM thread_edges WHERE thread_ref=? ORDER BY id", (thread_ref,))]
    con.close()
    for e in rows:
        e["source"] = _stale_text(e.get("source") or "", ds)
    return rows


# ---------------------------------------------------------------- collaboration stats
def collab_stats(inc, stage=None):
    """Collaboration around an incident — optionally filtered to one lifecycle stage."""
    import collab
    cs = collab.comments(inc["id"])
    ds = collab.delegations(inc["id"])
    if stage:
        cs = [c for c in cs if (c.get("stage") or "") == stage]
        ds = [d for d in ds if (d.get("stage") or "") == stage]
    seen = {}
    for c in cs:
        a = c["author"]
        if a == "Recommendation engine" or a in seen:
            continue
        seen[a] = c.get("channel") or "App"
    participants = sorted(seen)
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
            "coord_min": coord_min, "updates": len(cs),
            "participants_detail": [{"who": a, "channel": ch} for a, ch in seen.items()]}


def verdict(rows, applied):
    """Overall recovery verdict from independently-checked rows.

    Investigating — nothing executed yet. Verified — every check passed. Mitigated — some passed.
    Recovery failed — every check failed on evidence. Inconclusive — applied, but the checks could
    not be decided (a missing source, a timeout); it is NOT a pass and NOT a failure."""
    if not applied or not rows:
        return "Investigating"
    results = [str(r.get("result", "")).strip() for r in rows]
    oks = [r.startswith("✅") for r in results]
    fails = [r.startswith("✖") or r.startswith("❌") for r in results]
    if all(oks):
        return "Verified"
    if any(oks):
        return "Mitigated"
    if all(fails):
        return "Recovery failed"
    return "Inconclusive"


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
    """The verdict every view must agree on: persisted record → closed (Verified) → session."""
    rec = resolution_record(inc["id"])
    if rec and rec.get("verdict"):
        return rec["verdict"]
    if (inc.get("status") or "").lower() == "closed":
        return "Verified"
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
    elif verdict == "Inconclusive":
        return "Inconclusive — the checks could not be decided; treat as NOT verified."
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


def render_timeline(inc_id, limit=None):
    rows = timeline(inc_id)
    if limit and len(rows) > limit:
        st.caption(f'Latest {limit} of {len(rows)} events — full history in the Timeline section.')
        rows = rows[-limit:]
    viz.timeline(rows)


def render_hypotheses(hyps, title="Root cause — ranked hypotheses (suspected vs confirmed)", limit=None):
    hyps = rank(hyps)
    st.markdown(f"**{title}**")
    if not hyps:
        st.info("No signal linked yet.")
        return hyps
    total = len(hyps)
    viz.hypothesis_cards(hyps[:limit] if limit else hyps, total=total, offset=0)
    if limit and len(hyps) > limit:
        with st.expander(f"Show all {len(hyps)} hypotheses"):
            viz.hypothesis_cards(hyps[limit:], total=total, offset=limit)
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
    # v103: the clock lives in the hero. The record states the *outcome*, not the number again.
    outcome = "breached" if str(sla_txt).strip().upper() == "BREACHED" else "within SLA"
    if verdict == "Verified":
        st.success(f'Incident **{inc_id}** independently **verified and closed** · SLA {outcome} '
                   f'· owner: {owner}.')
        st.markdown(f'**Learning:** evidence captured → runbook / known-error updated.{(" " + extra) if extra else ""}')
    elif verdict == "Mitigated":
        st.warning(f'Fix applied but **NOT verified** — incident **{inc_id}** remains **OPEN** · SLA {outcome} · '
                   f'owner {owner}. Partial recovery only — further action required.')
    elif verdict == "Inconclusive":
        return "Inconclusive — the checks could not be decided; treat as NOT verified."
    elif verdict == "Recovery failed":
        st.error(f'Recovery **FAILED** — incident **{inc_id}** remains **OPEN** · SLA {outcome} · owner {owner}. '
                 f'Escalate.')
    else:
        st.info(f'Incident **{inc_id}** — status: {verdict or "investigating"} (not closed).')


_STATUS_COLOR = {"assigned": "#d97706", "accepted": "#0891b2", "reopened": "#b91c1c",
                 "done": "#16a34a"}


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
    st.markdown('<span class="ri-tag" style="background:#16a34a">Coordination — autonomous under '
                'policy</span> <span style="color:#64748b;font-size:12px">(assign + notify carries no '
                'production risk)</span>', unsafe_allow_html=True)
    if delegs:
        st.markdown("**Collaboration status**")
        for d in delegs:
            col = _STATUS_COLOR.get(d["status"], "#64748b")
            st.markdown(f'<div class="ri-ev-chip" style="border-left-color:{col}"><b>{d["frm"]} → '
                        f'{d["to_"]}</b> · {d["action"]} · <span class="ri-tag" style="background:{col}">'
                        f'{d["status"]}</span></div>', unsafe_allow_html=True)
    if auto:
        st.caption("🤖 Auto-coordinate is ON — the agent engaged the next actor automatically under policy. "
                   "The production change below still requires approval.")
    else:
        st.button("Coordinate — delegate & notify", key="engage_" + ref,
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
    """Single-step-at-a-time wizard with one progress metaphor and a handshake into each stage.

    Each stage renders inside a keyed container so the page can jump to it: the workspace's primary
    action ("Confirm cause", "Execute fix", …) and the step control both land the reader on the
    section they just asked for, instead of at the top of a long page."""
    if key not in st.session_state or st.session_state.get(key) not in steps:
        st.session_state[key] = steps[default]
    st.radio("Step", steps, horizontal=True, key=key)
    step = st.session_state[key]
    if st.session_state.get(key + "_prev") != step:
        st.session_state[key + "_prev"] = step
        st.session_state.setdefault("_scroll_anchor", f"{key}_anchor_{step}")
    viz.resolution_flow(current=step)
    if handoffs and step in handoffs:
        viz.handshake(handoffs[step])          # the handshake BEFORE this stage's content
    if help and step in help:
        st.markdown(f'<div class="ri-card" style="background:#f8fafc;padding:9px 13px;margin:2px 0 10px">'
                    f'<b>What this stage is:</b> {help[step]}</div>', unsafe_allow_html=True)
    with st.container(key=f"{key}_anchor_{step}"):
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
    st.info(f'Shared root cause **{c["shared_cause"]}** links this to **{c["other_domain"]} '
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


# ---------------------------------------------------------------- closure gate (v78)
def closure_state(inc):
    """The single authority on whether an incident may be closed.

    Closure needs an independent verification that passed, no outstanding collaboration request, and
    the incident not already closed. Everything else is a stated reason, never a silent block."""
    import collab
    rec = resolution_record(inc["id"])
    verdict = (rec or {}).get("verdict")
    closed = (inc.get("status") or "").lower() == "closed"
    reasons = []
    asks = [d for d in collab.delegations(inc["id"]) if d["status"] != "done"]
    if closed:
        return {"eligible": False, "closed": True, "verdict": verdict or "Verified",
                "reasons": [], "record": rec}
    if not rec or not rec.get("checks"):
        reasons.append("No verification record yet — apply a remediation and let the independent checks run.")
    elif verdict != "Verified":
        reasons.append(f"Authoritative verdict is **{verdict}** — closure requires **Verified**.")
        for c in (rec.get("checks") or []):
            if not str(c.get("result", "")).startswith("✅"):
                reasons.append(f'Failing check · {c.get("check") or c.get("metric") or "check"} → {c.get("result")}')
    if asks:
        reasons.append(f'{len(asks)} open collaboration request(s) — complete or withdraw them first.')
    return {"eligible": not reasons, "closed": False, "verdict": verdict or "Investigating",
            "reasons": reasons, "record": rec}


def close_incident(inc_id, actor="Incident Manager"):
    """Close an incident — only through the gate. Returns (ok, message)."""
    import collab
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = None
    for table in ("incidents", "dop_incidents"):
        r = con.execute(f"SELECT * FROM {table} WHERE id=?", (inc_id,)).fetchone()
        if r:
            row = dict(r)
            table_hit = table
            break
    con.close()
    if row is None:
        return False, "Incident not found."
    state = closure_state(row)
    if state["closed"]:
        return False, "Already closed."
    if not state["eligible"]:
        return False, state["reasons"][0] if state["reasons"] else "Closure blocked."
    con = sqlite3.connect(DB)
    con.execute(f"UPDATE {table_hit} SET status='closed' WHERE id=?", (inc_id,))
    now = dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    con.execute("UPDATE resolution_state SET closed_at=?, updated_at=? WHERE ref_id=?", (now, now, inc_id))
    con.commit()
    con.close()
    add_event(inc_id, "itops" if table_hit == "incidents" else "dataops", "verify",
              f"Closure gate passed — closed by {actor} on the verified record")
    collab.add_comment(inc_id, actor, "Person",
                       "[Simulated] Closed on the authoritative verification record.", channel="App")
    return True, "Incident closed on the verified record."


# ---------------------------------------------------------------- next action (v83)
def _ensure_confirmed_at():
    """Both incident tables carry confirmed_at; add it lazily for databases seeded before v85."""
    con = sqlite3.connect(DB)
    for table in ("incidents", "dop_incidents"):
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN confirmed_at TEXT")
        except Exception:
            pass
    con.commit()
    con.close()


def confirmed_at(inc_id):
    """When the root cause was confirmed, or None. Prefers the recorded column, then the evidence trail."""
    _ensure_confirmed_at()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for table in ("incidents", "dop_incidents"):
        r = con.execute(f"SELECT confirmed_at FROM {table} WHERE id=?", (inc_id,)).fetchone()
        if r and r["confirmed_at"]:
            con.close()
            try:
                return dt.datetime.fromisoformat(r["confirmed_at"])
            except Exception:
                return None
    con.close()
    for ev in reversed(timeline(inc_id)):
        if "root cause confirmed" in (ev.get("detail") or "").lower():
            try:
                return dt.datetime.fromisoformat(ev["ts"])
            except Exception:
                return None
    return None


def next_action(inc, stage=None):
    """The single next thing to do, derived from EVIDENCE rather than the recorded stage name.

    Confirming the cause must move the product on: the primary action becomes "bring in the owner",
    then "execute the fix", then "verify", then "close". A stage label that lags behind the evidence
    must never leave the button stuck on a step the user has already done."""
    import collab
    rec = resolution_record(inc["id"])
    verdict = (rec or {}).get("verdict") or current_verdict(inc)
    applied = applied_action(inc["id"])
    closed = (inc.get("status") or "").lower() == "closed"
    confirmed = bool(inc.get("confirmed_cause"))
    confirmed_ts = confirmed_at(inc["id"])
    open_asks = [d for d in collab.delegations(inc["id"]) if d["status"] != "done"]
    # A handoff raised before the cause was confirmed was for a different question; it does not mean
    # this cause has an owner behind it. Coordination counts only from a request made after confirmation.
    def _after_confirmation(d):
        if not confirmed_ts:
            return True
        try:
            return dt.datetime.fromisoformat(d["ts"]) > confirmed_ts
        except Exception:
            return False

    deleg = any(_after_confirmation(d) for d in open_asks)
    stage = stage or lifecycle_stage(inc)

    if closed:
        import learn
        if not learn.get(inc["id"]):
            return {"label": "Capture the learning", "stage": "Learn",
                    "why": "Closed on the verified record — capture what worked before moving on.",
                    "state": "closed"}
        return {"label": None, "stage": "Learn", "why": "Closed on the verified record.",
                "state": "closed"}
    if applied and verdict == "Verified":
        return {"label": "Close incident", "stage": "Close",
                "why": "Verification passed — closure is now allowed.", "state": "verified"}
    if applied:
        return {"label": "Verify now", "stage": "Verify",
                "why": f"Execution recorded; the verdict is {verdict}. Verification decides the rest.",
                "state": "applied"}
    if not confirmed:
        return {"label": "Confirm cause", "stage": "Correlate",
                "why": "Weigh the observed evidence against the inferred links before acting.",
                "state": "unconfirmed"}
    if deleg:
        return {"label": "Execute fix", "stage": "Act",
                "why": "Cause confirmed and an owner is engaged — execute the approved remediation.",
                "state": "delegated"}
    if confirmed:
        return {"label": "Bring in owner", "stage": "Act",
                "why": "Root cause confirmed. Get the owner and the approval on the thread with a deadline.",
                "state": "confirmed"}
    return {"label": "Review evidence", "stage": "Correlate", "why": "", "state": "unknown"}
