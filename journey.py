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


def timeline(ref_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM timeline WHERE ref_id=? ORDER BY ts", (ref_id,))]
    con.close()
    return rows


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
    rows = timeline(inc_id)
    st.markdown("**Operational timeline (time-correlated across systems)**")
    for r in rows:
        st.write(f'- `{r["ts"]}` {KIND_ICON.get(r["kind"], "•")} **{r["kind"]}** — {r["detail"]}')


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


def render_resolution(inc_id, applied, sla_txt, owner, extra=""):
    if not applied:
        return
    st.markdown("**Resolution record**")
    st.success(f'Incident **{inc_id}** independently verified and closed · SLA outcome: **{sla_txt}** · owner: {owner}.')
    st.markdown(f'**Learning:** evidence captured → runbook / known-error updated.{(" " + extra) if extra else ""}')


def render_recovery_update(title, body):
    st.markdown(f"**{title} — evidence-backed recovery update**")
    st.success(body)


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
        if st.button(f'View {c["other_id"]} in DataOps →', key="go_dop_" + inc_id):
            st.session_state["ops_domain"] = "DataOps"
            st.session_state["dop_inc"] = c["other_id"]
            st.rerun()
    else:
        if st.button(f'View {c["other_id"]} in IT Ops →', key="go_it_" + inc_id):
            st.session_state["ops_domain"] = "IT Ops"
            st.session_state["it_inc"] = c["other_id"]
            st.rerun()
