#!/usr/bin/env python3
"""Learn — the durable record of what actually worked.

Everything else in the demo lives in a per-session copy of ``ops.db`` (a refresh resets it).
Learning is the one artefact that must survive a reload, so it is written to its own JSON document
(``data/learn.json``; override with ``RI_LEARN_PATH``). Nothing here is inferred after the fact: a
record holds what the operator confirmed, the summary they wrote, the steps that actually worked,
the verification outcome with who and when, and the evidence carried over from the thread.

Records are matched by SIGNATURE — ``domain | failing component | cause class`` — so a new incident
can see what fixed the last incident with the same signature. A record saved *after* an incident was
raised cannot have helped resolve it; the analytics module compares timestamps to keep that honest.
"""
import datetime as dt
import json
import os
import sqlite3

DB = os.environ.get("RI_DB", "data/ops.db")
PATH = os.environ.get("RI_LEARN_PATH", "data/learn.json")

OUTCOMES = ("confirmed", "overridden", "rejected")
OUTCOME_LABEL = {"confirmed": "Confirmed — the verified cause held",
                 "overridden": "Overridden — the recorded cause was replaced",
                 "rejected": "Rejected — no cause was established"}


# ---------------------------------------------------------------- storage
def _now():
    return dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def _iso_days_ago(days):
    return (dt.datetime.now() - dt.timedelta(days=days)).replace(microsecond=0).isoformat(timespec="seconds")


def _read():
    try:
        with open(PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        recs = _seed()
        try:
            _write(recs)
        except OSError:
            pass                     # a read-only checkout still renders; saving reports the error
        return recs
    except Exception:
        return []


def _write(recs):
    folder = os.path.dirname(PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(recs, fh, indent=2, sort_keys=True)
    os.replace(tmp, PATH)


def records():
    """Every learn record, newest first."""
    return sorted(_read(), key=lambda r: r.get("saved_at") or "", reverse=True)


def get(ref):
    return next((r for r in _read() if r.get("ref") == ref), None)


def incident_row(ref):
    """(row, domain) for an incident in either table — used to derive a signature from a ref."""
    try:
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
    except Exception:
        return None, None
    try:
        for table, domain in (("incidents", "IT Ops"), ("dop_incidents", "DataOps")):
            try:
                r = con.execute(f"SELECT * FROM {table} WHERE id=?", (ref,)).fetchone()
            except Exception:
                continue
            if r:
                return dict(r), domain
    finally:
        con.close()
    return None, None


# ---------------------------------------------------------------- identity of a failure
def signature(inc, domain):
    """The failure signature: domain | failing component | cause class.

    The cause class comes from the confirmed cause key (``UPSTREAM:ds_pay_gd`` → ``UPSTREAM``).
    An incident with no confirmed cause is *unclassified* — it must not claim to match a class it
    has not established."""
    comp = inc.get("dataset_id") if domain == "DataOps" else inc.get("service_id")
    key = (inc.get("confirmed_cause") or "").strip()
    cls = key.split(":")[0] if key else "unclassified"
    return f'{"dop" if domain == "DataOps" else "it"}|{comp or "unknown"}|{cls}'


def signature_for_ref(ref):
    row, domain = incident_row(ref)
    return signature(row, domain) if row else None


def similar(sig, exclude_ref=None):
    return [r for r in records() if r.get("signature") == sig and r.get("ref") != exclude_ref]


def reuse_candidates(sig, exclude_ref=None):
    """Prior records an operator could say they applied: the same signature first."""
    same = similar(sig, exclude_ref)
    others = [r for r in records() if r.get("signature") != sig and r.get("ref") != exclude_ref]
    return same + others


# ---------------------------------------------------------------- evidence carried over
def thread_evidence(inc, domain):
    """The evidence the thread already holds — carried into the record, not retyped."""
    import journey
    out = []
    for ev in journey.timeline(inc["id"]):
        out.append(f'{ev["kind"]}: {ev["detail"]}')
    if domain != "DataOps":
        for e in journey.thread_edges_for(inc["id"]):
            out.append(f'source: {e["src"]} → {e["dst"]} ({e["kind"]}) · {e["source"]}')
    rec = journey.resolution_record(inc["id"])
    for c in (rec or {}).get("checks") or []:
        out.append(f'check: {c.get("check") or c.get("metric")} → {c.get("result")}')
    return out[:12]


# ---------------------------------------------------------------- the cause decision
def cause_decision(inc):
    """What the verification trail says about the cause: confirmed / overridden / rejected.

    Derived from the recorded confirmation and the verify events on the timeline — never guessed
    from the stage name. Returns who/when where the record carries them."""
    import journey
    confirmed_key = (inc.get("confirmed_cause") or "").strip()
    detail = [str(e.get("detail") or "").lower() for e in journey.timeline(inc["id"])
              if e.get("kind") == "verify"]
    rejected = any("hypothesis rejected" in d for d in detail)
    confirmations = [d for d in detail if "root cause confirmed" in d]
    if confirmed_key and rejected and len(confirmations) > 1:
        outcome = "overridden"
    elif confirmed_key:
        outcome = "confirmed"
    elif rejected:
        outcome = "rejected"
    else:
        outcome = "confirmed"
    when = None
    ts = journey.confirmed_at(inc["id"])
    if ts:
        when = ts.replace(microsecond=0).isoformat(timespec="seconds")
    return {"outcome": outcome, "by": inc.get("owner_team") or "Incident Manager", "at": when}


# ---------------------------------------------------------------- write
def save(inc, domain, fields, actor="Incident Manager"):
    """Create or replace the learn record for this incident. Returns the stored record."""
    ref = inc["id"]
    decision = cause_decision(inc)
    rec = {
        "ref": ref,
        "domain": domain,
        "title": inc.get("title") or ref,
        "signature": signature(inc, domain),
        "root_cause": (fields.get("root_cause") or "").strip(),
        "summary": (fields.get("summary") or "").strip(),
        "steps": [s.strip(" -•\t") for s in str(fields.get("steps") or "").splitlines() if s.strip(" -•\t")],
        "outcome": fields.get("outcome") if fields.get("outcome") in OUTCOMES else decision["outcome"],
        "outcome_by": (fields.get("outcome_by") or decision["by"] or actor).strip(),
        "outcome_at": fields.get("outcome_at") or decision["at"] or _now(),
        "evidence": list(fields.get("evidence") or thread_evidence(inc, domain)),
        "reused_from": fields.get("reused_from") or None,
        "saved_at": _now(),
        "saved_by": actor,
    }
    recs = [r for r in _read() if r.get("ref") != ref]
    recs.append(rec)
    _write(recs)
    # the graph reads learn records too: re-project so the new record shows in Connections without
    # waiting for the next session
    try:
        import graph
        graph.project(DB)
    except Exception:
        pass
    return rec


# ---------------------------------------------------------------- seed (sample data)
def _mk(ref, domain, title, comp, cls, root, summary, steps, outcome, by, days, reused=None,
        evidence=None):
    return {
        "ref": ref, "domain": domain, "title": title,
        "signature": f'{"dop" if domain == "DataOps" else "it"}|{comp}|{cls}',
        "root_cause": root, "summary": summary, "steps": steps,
        "outcome": outcome, "outcome_by": by, "outcome_at": _iso_days_ago(days),
        "evidence": evidence or [], "reused_from": reused,
        "saved_at": _iso_days_ago(days), "saved_by": by,
    }


def _seed():
    """Sample records so the Learn list, the similarity match and the metrics have data on day one.

    Two of the three closed incidents have a prior record with their own signature (a real head
    start); the third has no record yet — it is the one that still needs capturing, and it is what
    the "without a prior record" group measures. The stale-upstream record is the one a newly
    confirmed INC-8841 will match."""
    return [
        _mk("INC-8802", "IT Ops", "Checkout latency after deploy", "app_checkout", "unclassified",
            "Release 24.07 exhausted the checkout connection pool.",
            "Rolled back the release, pool back to baseline, latency within threshold.",
            ["Rolled back release 24.07 on checkout-api",
             "Reset the checkout connection pool to its baseline size",
             "Confirmed p95 latency < 800 ms for 30 minutes"],
            "confirmed", "Checkout Team lead", 30, reused="INC-8711",
            evidence=["alert: checkout p95 latency above 800 ms", "change: release 24.07 deployed"]),
        _mk("INC-8711", "IT Ops", "DB connection pool exhaustion", "db_payments", "unclassified",
            "A leaking session batch exhausted the payments-db connection pool.",
            "Pool limit raised under DBA approval; the leaking batch was killed.",
            ["Raised the payments-db connection limit under DBA approval",
             "Killed the leaking session batch",
             "Added a pool-saturation alert at 80%"],
            "confirmed", "DBA Team", 40,
            evidence=["alert: active_connections above 700"]),
        _mk("INC-8462", "IT Ops", "Payment API serving stale risk data (schema drift)",
            "its_payment_api", "UPSTREAM",
            "core_ledger schema drift left payments_gold stale; the API served stale risk data.",
            "Contract reconciled, pipeline replayed, payments_gold fresh again.",
            ["Reconciled the core_ledger schema with data contract v4",
             "Replayed payments_bronze_ingest",
             "Refreshed payments_gold and restarted the payment service"],
            "confirmed", "Data Platform", 10,
            evidence=["source: Pipeline failure → payments_gold stale (observed)"]),
        _mk("INC-8588", "DataOps", "orders_bronze_ingest schema drift", "ds_orders_bz", "RUN",
            "The source feed added order_channel; the contract was out of date.",
            "Contract updated and the batch replayed.",
            ["Updated the orders contract to include order_channel", "Replayed the failed batch"],
            "overridden", "Data Owner", 5,
            evidence=["alert: run failed SCHEMA_MISMATCH 'order_channel'"]),
    ]


# ---------------------------------------------------------------- UI
def panel(inc, domain, actor="Incident Manager"):
    """The Learn stage: the draft is already filled from the thread, editable, then saved durably."""
    import streamlit as st
    ref = inc["id"]
    sig = signature(inc, domain)
    rec = get(ref)
    st.markdown("#### Learn — capture what worked, so the next incident starts ahead")
    st.caption(f'Signature **{sig}** · matches past incidents on the same component and cause class.')
    closed = (inc.get("status") or "").lower() == "closed"
    if rec:
        _render_saved(rec, inc)
        with st.expander("Edit this learn record", expanded=False):
            _form(inc, domain, actor, sig, existing=rec)
    else:
        if not closed:
            st.info("This incident is still open. The draft below is filled from the thread; the record "
                    "is saved when the incident is closed and verified.")
        _form(inc, domain, actor, sig, existing=None)
    _similar_block(sig, ref)


def _render_saved(rec, inc):
    import streamlit as st
    st.success(f'Learn record saved · {rec.get("saved_at")} · by {rec.get("saved_by")}')
    st.markdown(f'**Root cause** — {rec.get("root_cause") or "—"}')
    st.markdown(f'**Resolution summary** — {rec.get("summary") or "—"}')
    st.markdown("**Steps that worked (runbook draft)**")
    for i, s in enumerate(rec.get("steps") or [], 1):
        st.markdown(f'{i}. {s}')
    label = OUTCOME_LABEL.get(rec.get("outcome"), rec.get("outcome") or "—")
    st.markdown(f'**Cause verification** — {label} · {rec.get("outcome_by") or "—"} · '
                f'{rec.get("outcome_at") or "—"}')
    if rec.get("reused_from"):
        st.markdown(f'**Reuse** — applied the fix recorded for **{rec["reused_from"]}**.')
    with st.expander(f'Evidence carried over ({len(rec.get("evidence") or [])})', expanded=False):
        for e in rec.get("evidence") or []:
            st.caption(f'· {e}')


def _form(inc, domain, actor, sig, existing=None):
    import streamlit as st
    decision = cause_decision(inc)
    existing = existing or {}
    steps_now = "\n".join(existing.get("steps") or _draft_steps(inc))
    key = f'learn_{inc["id"]}'
    with st.form(key=key + "_form", clear_on_submit=False, border=False):
        root = st.text_area("Root cause", value=existing.get("root_cause") or _draft_root(inc),
                            height=80, key=key + "_root")
        summary = st.text_area("Resolution summary", value=existing.get("summary") or (inc.get("summary") or ""),
                               height=80, key=key + "_sum")
        steps = st.text_area("Steps that actually worked — one per line (runbook draft)",
                             value=steps_now, height=130, key=key + "_steps")
        c1, c2 = st.columns(2)
        options = list(OUTCOMES)
        cur = existing.get("outcome") or decision["outcome"]
        outcome = c1.selectbox("Cause verification outcome", options, index=options.index(cur),
                               format_func=lambda o: o.title(), key=key + "_out")
        by = c2.text_input("Decided by", value=existing.get("outcome_by") or decision["by"] or actor,
                           key=key + "_by")
        cands = reuse_candidates(sig, exclude_ref=inc["id"])
        reuse_opts = ["—"] + [f'{r["ref"]} · {r["title"][:44]}' for r in cands]
        cur_reuse = existing.get("reused_from")
        idx = 0
        for i, r in enumerate(cands, 1):
            if r["ref"] == cur_reuse:
                idx = i
        reuse = st.selectbox("Applied a prior learn record?", reuse_opts, index=idx,
                             key=key + "_reuse",
                             help="Recorded so reuse is measured, not claimed.")
        evidence = thread_evidence(inc, domain)
        with st.expander(f'Evidence carried over from the thread ({len(evidence)})', expanded=False):
            for e in evidence:
                st.caption(f'· {e}')
        closed = (inc.get("status") or "").lower() == "closed"
        saved = st.form_submit_button("Save learn record" if closed else "Save draft record",
                                      type="primary", disabled=False)
    if saved:
        reused_from = cands[idx - 1]["ref"] if idx > 0 and idx - 1 < len(cands) else None
        try:
            save(inc, domain, {"root_cause": root, "summary": summary, "steps": steps,
                               "outcome": outcome, "outcome_by": by, "evidence": evidence,
                               "reused_from": reused_from,
                               "outcome_at": existing.get("outcome_at") or decision["at"]}, actor=actor)
        except Exception as exc:                       # never pretend a write happened
            st.error(f'Could not write the learn record: {exc}')
        else:
            st.session_state["flash"] = (f'Learn record saved for **{inc["id"]}** — it now appears in the '
                                         f'Learn list and in similarity matches.')
            st.rerun()


def _draft_root(inc):
    key = (inc.get("confirmed_cause") or "").strip()
    if key:
        return f'Confirmed cause {key} — {inc.get("title") or ""}'
    return inc.get("blocker") or inc.get("summary") or inc.get("title") or ""


def _draft_steps(inc):
    """Prefill from the action that was actually executed on this incident, if any."""
    import journey
    action_id = journey.applied_action(inc["id"])
    if not action_id:
        return []
    try:
        if (inc.get("dataset_id")):
            import dataops_engine as DE
            opt = next((o for o in DE.DOP_REMEDIATION if o["id"] == action_id), None)
        else:
            import engine as E
            opt = next((o for o in E.IT_REMEDIATION if o["id"] == action_id), None)
    except Exception:
        opt = None
    return [opt["label"]] if opt else []


def _similar_block(sig, ref):
    import streamlit as st
    hits = similar(sig, exclude_ref=ref)
    st.markdown(f'**Similar past incidents — same signature ({len(hits)})**')
    if not hits:
        st.caption("No earlier incident with this signature. Saving this record is what makes the next "
                   "one faster.")
        return
    for r in hits:
        fixed = "; ".join(r.get("steps") or []) or "—"
        st.markdown(
            f'<div class="ri-card" style="padding:9px 12px;margin:6px 0">'
            f'<b>{r["ref"]}</b> · {r["title"]} · outcome <b>{r.get("outcome")}</b> · '
            f'{r.get("saved_at")}<div style="font-size:12.5px;color:#475569;margin-top:4px">'
            f'<b>What fixed it</b> · {fixed}</div></div>',
            unsafe_allow_html=True)
