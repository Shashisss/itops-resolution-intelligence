#!/usr/bin/env python3
"""Resolution analytics — every number measured from stored lifecycle timestamps.

Pure functions over SQLite: no Streamlit, no rendering, no session state, so the same code can be
tested headlessly and reused by any view. The database path comes from the caller rebinding this
module's ``DB`` at start-up (app.py does ``analytics.DB = store.db()``), exactly like journey/collab.

What is measured, and from where
--------------------------------
MTTR             resolution_state.closed_at − incidents.created_at, verified verdicts only.
Stage durations  consecutive lifecycle anchors per incident. Anchor sources:
                   • timeline events, mapped by kind (alert/impact/change/incident → Detect,
                     ticket → Correlate, repair → Act, verify → Verify, and a "Closure gate passed"
                     event → Close);
                   • stage-tagged comments (comments.stage is one of the six lifecycle stages);
                   • the first delegation (coordination started) → Coordinate;
                   • resolution_state.closed_at → Close.
                 A stage's duration is the time from its first anchor to the next stage's first
                 anchor. Stages whose next stage has not happened yet are *unmeasured*, never zero.
OLA vs actual    stage_olas.target_min against the measured stage medians (delta = actual − target).
Outcomes         resolution_state.verdict counts; the denominator is records, not incidents.
Handoff delay    delegations.done_at − delegations.ts (done_at is written when a request is
                 completed; never backfilled). Open requests older than 30 minutes are reported
                 separately — an unfinished request has no delay and must not be counted as zero.
SLA load         incidents.created_at + personas.SLA_HOURS; a closed incident is measured to its
                 recorded closure time, an open one to now.

Anything the data cannot support comes back as ``None`` with ``n=0`` — the caller labels it, this
module never fills a gap with an estimate.
"""
import datetime as dt
import math
import os
import sqlite3
import statistics

DB = os.environ.get("RI_DB", "data/ops.db")

STAGES = ["Detect", "Triage", "Investigate", "Correlate", "Act", "Verify", "Close", "Learn"]

# Timeline kinds are the recorded signals; they are mapped onto the one shared lifecycle vocabulary.
KIND_STAGE = {
    "alert": "Detect", "impact": "Detect", "change": "Detect", "incident": "Detect",
    "ticket": "Triage", "repair": "Act", "verify": "Verify", "close": "Close",
}

# Stage names recorded before v98 (Coordinate, Triaged, Diagnosed …) still map onto the one list.
LEGACY_STAGE = {
    "Coordinate": "Act", "Detected": "Detect", "Triaged": "Triage", "Diagnosed": "Correlate",
    "Change raised": "Act", "Fix in progress": "Act", "Fix applied": "Verify",
    "Verified": "Verify", "Closed": "Close", "Backfilled": "Verify", "Validated": "Verify",
    "Learned": "Learn",
}

# Fallback OLA targets, identical to what the app seeds and to engine.load_stage_olas(). The table
# is authoritative when it exists; these only keep the module usable on an un-migrated database.
STAGE_OLA_DEFAULT = {"Detect": 5, "Triage": 10, "Investigate": 20, "Correlate": 15, "Act": 30,
                     "Verify": 30, "Learn": 60}

DEFAULT_SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

# A panel with fewer samples than this is reported, but labelled indicative rather than significant.
MIN_SIGNIFICANT = 5


# ---------------------------------------------------------------- plumbing
def _connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _rows(sql, params=()):
    con = _connect()
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def _table_exists(name):
    return bool(_rows("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def _ts(value):
    """ISO string → naive datetime, or None when it is missing/unparseable."""
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _minutes(later, earlier):
    a, b = _ts(later), _ts(earlier)
    if a is None or b is None:
        return None
    return round((a - b).total_seconds() / 60.0, 1)


def _pct(values, p):
    """Percentile, linear interpolation — deterministic and dependency-free."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return round(vals[0], 1)
    k = (len(vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return round(vals[int(k)], 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 1)


def _median(values):
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 1) if vals else None


def incidents():
    """Every incident, IT and DataOps, with its stored timing."""
    out = []
    for table, domain, comp in (("incidents", "IT Ops", "service_id"),
                                ("dop_incidents", "DataOps", "dataset_id")):
        for r in _rows(f"SELECT id,title,priority,status,created_at,owner_team,stage,"
                       f"{comp} AS component FROM {table}"):
            r["domain"] = domain
            r[comp] = r.pop("component")
            out.append(r)
    return out


def _resolution_records():
    if not _table_exists("resolution_state"):
        return {}
    return {r["ref_id"]: r for r in _rows("SELECT * FROM resolution_state")}


def sla_hours():
    """The SLA targets the rest of the app uses. Imported lazily so this module stays UI-free."""
    try:
        import personas
        table = getattr(personas, "SLA_HOURS", None)
        if table:
            return dict(table)
    except Exception:
        pass
    return dict(DEFAULT_SLA_HOURS)


# ---------------------------------------------------------------- panels
def mttr():
    """Median and p90 time from raise to verified closure. Incidents with no resolution record are
    excluded outright — a missing record is unknown, not zero."""
    inc = {i["id"]: i for i in incidents()}
    records = _resolution_records()
    values, rows = [], []
    for ref, rec in records.items():
        if (rec.get("verdict") or "") != "Verified" or not rec.get("closed_at"):
            continue
        i = inc.get(ref)
        if not i:
            continue
        mins = _minutes(rec["closed_at"], i.get("created_at"))
        if mins is None:
            continue
        values.append(mins)
        rows.append({"ref": ref, "domain": i["domain"], "priority": i.get("priority"),
                     "created_at": i.get("created_at"), "closed_at": rec["closed_at"], "minutes": mins})
    rows.sort(key=lambda r: r["minutes"], reverse=True)
    return {
        "median_min": _median(values),
        "p90_min": _pct(values, 0.9),
        "n": len(values),
        "values": values,
        "closures": rows,
        "excluded_no_record": max(0, len(inc) - len(records)),
        "excluded_unverified": sum(1 for r in records.values()
                                   if (r.get("verdict") or "") != "Verified"),
    }


def _stage_anchors(ref, closed_at):
    """Ordered (stage, ts) anchors for one incident — one per stage, monotonic in lifecycle order.

    Evidence is ranked, not blended: a stage-tagged comment is an explicit statement that the stage
    was reached, so it wins; a timeline event is a signal mapped onto a stage; a handoff only says
    coordination exists. A weaker source never overwrites a stronger one."""
    anchors = {}

    def add(stage, ts, overwrite=False):
        if stage not in STAGES or not ts:
            return
        prev = anchors.get(stage)
        if prev is None or overwrite:
            anchors[stage] = ts

    for cm in _rows("SELECT ts,stage FROM comments WHERE ref_id=? ORDER BY ts", (ref,)):
        raw = str(cm.get("stage") or "").strip().title()
        add(LEGACY_STAGE.get(raw, raw), cm.get("ts"))
    for ev in _rows("SELECT ts,kind,detail FROM timeline WHERE ref_id=? ORDER BY ts", (ref,)):
        detail = str(ev.get("detail") or "").lower()
        stage = "Close" if "closure gate passed" in detail else KIND_STAGE.get(ev.get("kind"))
        add(stage, ev.get("ts"))
    dels = _rows("SELECT ts FROM delegations WHERE ref_id=? ORDER BY ts", (ref,))
    if dels:
        add("Act", dels[0].get("ts"))
    learn_ts = _learn_anchor(ref)
    if learn_ts:
        add("Learn", learn_ts)
    add("Close", closed_at)

    kept, last = [], None
    for stage in STAGES:                      # lifecycle order, not timestamp order
        ts = anchors.get(stage)
        if not ts:
            continue
        cur = _ts(ts)
        if cur is None:
            continue
        if last is not None and cur < last:
            continue                           # out of order against the stage before it — dropped
        kept.append((stage, ts))
        last = cur
    return kept


def _learn_anchor(ref):
    """A learn record is the Learn stage's anchor — its save time, never the closure time."""
    try:
        import learn
        rec = learn.get(ref)
        return (rec or {}).get("saved_at")
    except Exception:
        return None


def stage_durations():
    """Median minutes per lifecycle stage, from consecutive anchors per incident.

    Returns every stage (zero-sample stages included) so a chart never invents a category order."""
    records = _resolution_records()
    per_stage = {s: [] for s in STAGES}
    by_incident = []
    for i in incidents():
        anchors = _stage_anchors(i["id"], (records.get(i["id"]) or {}).get("closed_at"))
        if not anchors:
            continue
        measured = []
        for (stage, ts), (_, nxt) in zip(anchors, anchors[1:]):
            mins = _minutes(nxt, ts)
            if mins is None or mins < 0:
                continue
            per_stage[stage].append(mins)
            measured.append({"stage": stage, "minutes": mins})
        if measured:
            by_incident.append({"ref": i["id"], "domain": i["domain"], "stages": measured})
    rows = []
    for stage in STAGES:
        vals = per_stage[stage]
        rows.append({"stage": stage, "median_min": _median(vals), "n": len(vals),
                     "indicative": len(vals) < MIN_SIGNIFICANT})
    return {
        "rows": rows,
        "per_stage": per_stage,
        "by_incident": by_incident,
        "n_incidents": len(by_incident),
        "basis": "timeline events · stage-tagged comments · first handoff · recorded closure",
    }


def ola_vs_actual():
    """Stage OLA target against the measured median. Delta is actual − target: positive = over."""
    measured = {r["stage"]: r for r in stage_durations()["rows"]}
    targets = dict(STAGE_OLA_DEFAULT)
    if _table_exists("stage_olas"):
        for r in _rows("SELECT stage,target_min FROM stage_olas"):
            if r.get("target_min") is not None:
                targets[r["stage"]] = r["target_min"]
    rows = []
    for stage in STAGES:
        m = measured.get(stage) or {"median_min": None, "n": 0}
        target = targets.get(stage)
        actual = m.get("median_min")
        delta = round(actual - target, 1) if (actual is not None and target is not None) else None
        rows.append({
            "stage": stage,
            "target_min": target,
            "actual_min": actual,
            "delta_min": delta,
            "n": m.get("n", 0),
            "state": ("no data" if actual is None
                      else "within" if delta is not None and delta <= 0
                      else "over" if delta is not None else "no target"),
        })
    return {"rows": rows, "n": sum(r["n"] for r in rows)}


def outcomes():
    """Verdict counts from the authoritative records, plus the verified-closure rate."""
    records = _resolution_records()
    all_inc = incidents()
    counted = [r for r in records.values() if r.get("verdict")]
    categories = ["Verified", "Mitigated", "Recovery failed", "Inconclusive"]
    counts = {c: 0 for c in categories}
    other = 0
    for r in counted:
        v = r["verdict"]
        if v in counts:
            counts[v] += 1
        else:
            other += 1
    n_records = len(counted)
    return {
        "counts": counts,
        "other": other,
        "n_records": n_records,
        "n_incidents": len(all_inc),
        "no_record": len(all_inc) - n_records,
        "verified_rate": round(counts["Verified"] / n_records, 3) if n_records else None,
    }


def _done_at_column():
    """``done_at`` did not exist before v92 — select it as NULL on a database that lacks it."""
    cols = {r["name"] for r in _rows("PRAGMA table_info(delegations)")}
    return "done_at" if "done_at" in cols else "NULL AS done_at"


def handoff_delay():
    """Median minutes from a request to its completion, and how much coordination is still open.

    ``delegations.done_at`` did not exist before v92: requests completed earlier have no completion
    stamp and are left out of the median (they are not treated as instant)."""
    rows = _rows("SELECT id,ref_id,frm,to_,action,status,ts, " + _done_at_column() + " FROM delegations")
    delays, completed, open_rows = [], [], []
    now = dt.datetime.now().replace(microsecond=0)
    for r in rows:
        status = str(r.get("status") or "").lower()
        if status == "done" and r.get("done_at"):
            mins = _minutes(r["done_at"], r["ts"])
            if mins is not None and mins >= 0:
                delays.append(mins)
                completed.append({**r, "minutes": mins})
        elif status != "done":
            age = _minutes(now.isoformat(timespec="seconds"), r["ts"])
            open_rows.append({**r, "age_min": age})
    overdue = [r for r in open_rows if (r.get("age_min") or 0) > 30]
    completed.sort(key=lambda r: r["minutes"])
    return {
        "median_min": _median(delays),
        "n_done": len(delays),
        "completed": completed,
        "n_open": len(open_rows),
        "open_over_30": len(overdue),
        "open_share_over_30": round(len(overdue) / len(open_rows), 3) if open_rows else None,
        "open": sorted(open_rows, key=lambda r: (r.get("age_min") or 0), reverse=True),
        "n_total": len(rows),
        "no_stamp": sum(1 for r in rows
                        if str(r.get("status") or "").lower() == "done" and not r.get("done_at")),
    }


def sla_load():
    """SLA breaches per priority, measured from the raise time against the app's SLA targets."""
    hours = sla_hours()
    records = _resolution_records()
    now = dt.datetime.now().replace(microsecond=0)
    buckets = {p: {"priority": p, "sla_hours": h, "total": 0, "breaches": 0}
               for p, h in hours.items()}
    for i in incidents():
        pri = i.get("priority") or "P3"
        b = buckets.setdefault(pri, {"priority": pri, "sla_hours": hours.get(pri), "total": 0,
                                     "breaches": 0})
        b["total"] += 1
        rec = records.get(i["id"]) or {}
        end = rec.get("closed_at") or now.isoformat(timespec="seconds")
        elapsed_h = (_minutes(end, i.get("created_at")) or 0) / 60.0
        if b["sla_hours"] and elapsed_h > b["sla_hours"]:
            b["breaches"] += 1
    rows = []
    for pri in sorted(buckets, key=lambda p: (str(p)[0], p)):
        b = buckets[pri]
        b["breach_rate"] = round(b["breaches"] / b["total"], 3) if b["total"] else None
        rows.append(b)
    return {"rows": rows, "n": sum(b["total"] for b in rows),
            "breaches": sum(b["breaches"] for b in rows)}


# ---------------------------------------------------------------- v101: windowed views (used by Ask)
# The Ask box may only answer with the same computations these pages use, so the definitions live
# here and both callers share them. Each returns the SQL that was actually executed, with its
# parameters, so an answer card can show it without rebuilding it.
_STATUS_SQL = {"all": "", "open": "a.status = 'open'", "closed": "a.status = 'closed'",
               "failed": "COALESCE(r.verdict, '') = 'Recovery failed'"}


def created_between(start, end, status="all"):
    """Incidents created in [start, end) — IT and DataOps — optionally filtered by a status bucket.

    `failed` means the verified recovery failed; an incident without a resolution record is not a
    failure, it is unknown, so it is excluded rather than counted."""
    where, params = [], {}
    if start:
        where.append("a.created_at >= :start")
        params["start"] = start
    if end:
        where.append("a.created_at < :end")
        params["end"] = end
    if _STATUS_SQL.get(status):
        where.append(_STATUS_SQL[status])
    sql = ("WITH all_inc AS (\n"
           "  SELECT id, created_at, status FROM incidents\n"
           "  UNION ALL\n"
           "  SELECT id, created_at, status FROM dop_incidents\n"
           ")\n"
           "SELECT a.id, a.created_at, a.status, COALESCE(r.verdict, '') AS verdict\n"
           "FROM all_inc a LEFT JOIN resolution_state r ON r.ref_id = a.id"
           + ("\nWHERE " + " AND ".join(where) if where else ""))
    con = _connect()
    try:
        rows = [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()
    total = len(incidents())
    return {"n": len(rows), "rows": rows, "checked": total, "sql": sql,
            "params": params, "status": status}


def mttr_between(start=None, end=None):
    """MTTR for closures in [start, end) — the same filter as mttr(), restricted by closed_at.

    `mttr()` with no arguments must stay identical: the test suite asserts the two agree."""
    where = "r.verdict = 'Verified' AND r.closed_at IS NOT NULL"
    params = {}
    if start:
        where += " AND r.closed_at >= :start"
        params["start"] = start
    if end:
        where += " AND r.closed_at < :end"
        params["end"] = end
    sql = ("SELECT r.ref_id, r.closed_at, i.created_at\n"
           "FROM resolution_state r\n"
           "JOIN (SELECT id, created_at FROM incidents\n"
           "      UNION ALL SELECT id, created_at FROM dop_incidents) i ON i.id = r.ref_id\n"
           f"WHERE {where}")
    con = _connect()
    try:
        rows = [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()
    values = []
    for row in rows:
        mins = _minutes(row["closed_at"], row["created_at"])
        if mins is not None:
            values.append(mins)
    return {"median_min": _median(values), "p90_min": _pct(values, 0.9), "n": len(values),
            "values": values, "sql": sql, "params": params}


def held_by_domain(start, end, now=None):
    """Total minutes incidents spent waiting on each domain, for requests raised in [start, end).

    The clock is the request's own: raised → done (or now, when still open). A domain's total is the
    sum of the clocks of the requests addressed to its teams — the same delegation rows the
    coordination figures above use."""
    now = now or dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    sql = ("SELECT d.to_ AS team, COUNT(*) AS requests,\n"
           "       ROUND(SUM((julianday(COALESCE(d.done_at, :now)) - julianday(d.ts)) * 1440), 1) AS minutes\n"
           "FROM delegations d\n"
           "WHERE d.ts IS NOT NULL AND d.ts >= :start AND d.ts < :end\n"
           "GROUP BY d.to_ ORDER BY minutes DESC")
    con = _connect()
    try:
        rows = [dict(r) for r in con.execute(sql, {"now": now, "start": start, "end": end})]
    finally:
        con.close()
    teams = {r["team"]: r for r in rows if r.get("team")}
    domains = {}
    for team, r in teams.items():
        dom = "Data Platform" if team in DATA_TEAMS else "IT Ops"
        d = domains.setdefault(dom, {"domain": dom, "minutes": 0.0, "requests": 0})
        d["minutes"] = round(d["minutes"] + (r["minutes"] or 0), 1)
        d["requests"] += r["requests"]
    ranked = sorted(domains.values(), key=lambda d: d["minutes"], reverse=True)
    return {"rows": ranked, "teams": rows, "n": sum(r["requests"] for r in rows),
            "sql": sql, "params": {"now": now, "start": start, "end": end}}


DATA_TEAMS = {"Data Platform", "Data Engineer", "Data Owner", "Finance Data",
              "Analytics Engineering", "Data Consumer"}


def learning():
    """Learning metrics: cause-confirmation accuracy, reuse, and the size of the record set.

    Accuracy counts decisions — confirmed vs overridden — from the durable learn records. A rejected
    cause is a decision but not a confirmation, so it is reported separately. Every figure carries
    its n; an empty sample is None (rendered as a dash), never zero.
    """
    import learn
    recs = learn.records()
    counts = {o: sum(1 for r in recs if r.get("outcome") == o)
              for o in ("confirmed", "overridden", "rejected")}
    decided = counts["confirmed"] + counts["overridden"]
    reuse = [r for r in recs if r.get("reused_from")]
    return {
        "n_records": len(recs),
        "counts": counts,
        "n_decided": decided,
        "accuracy": round(counts["confirmed"] / decided, 3) if decided else None,
        "n_reused": len(reuse),
        "reuse_rate": round(len(reuse) / len(recs), 3) if recs else None,
        "reused": [{"ref": r["ref"], "from": r["reused_from"], "saved_at": r.get("saved_at")}
                   for r in reuse],
    }


def mttr_by_learn():
    """Median time-to-resolution with a prior learn record vs without one.

    "Prior" is strict: a record saved after the incident was raised cannot have helped resolve it,
    so it is not counted as knowledge the responder had. A group with no closures reports n=0 and
    no median — never a zero-minute improvement."""
    import learn
    incs = {i["id"]: i for i in incidents()}
    recs = _resolution_records()
    earliest = {}
    for r in learn.records():
        sig, ts = r.get("signature"), _ts(r.get("saved_at"))
        if sig and ts and (sig not in earliest or ts < earliest[sig]):
            earliest[sig] = ts
    groups = {"with": [], "without": []}
    rows = []
    for ref, rec in recs.items():
        if (rec.get("verdict") or "") != "Verified" or not rec.get("closed_at"):
            continue
        inc = incs.get(ref)
        if not inc:
            continue
        mins = _minutes(rec["closed_at"], inc.get("created_at"))
        if mins is None:
            continue
        sig = learn.signature(inc, inc.get("domain") or "IT Ops")
        prior = earliest.get(sig)
        created = _ts(inc.get("created_at"))
        matched = bool(prior and created and prior < created)
        groups["with" if matched else "without"].append(mins)
        rows.append({"ref": ref, "domain": inc.get("domain"), "minutes": mins, "matched": matched,
                     "signature": sig,
                     "prior_saved_at": prior.isoformat(timespec="seconds") if prior else None})
    return {
        "with": {"median_min": _median(groups["with"]), "n": len(groups["with"])},
        "without": {"median_min": _median(groups["without"]), "n": len(groups["without"])},
        "rows": rows,
    }


def summary():
    """One call for the page header tiles."""
    m, o, h, s = mttr(), outcomes(), handoff_delay(), sla_load()
    return {"mttr": m, "outcomes": o, "handoff": h, "sla": s}
