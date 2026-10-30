#!/usr/bin/env python3
"""The story in numbers — one definition per claim.

Three ideas have to be unmistakable on every incident screen: **cross-domain**, **collaboration**
and **accelerated resolution**. Every number that states one of them is computed here, once, from
the record:

- ``hero()``        the first three seconds — who holds it, the SLA clock, how many domains and handoffs
- ``chain()``       the handoff path as physical hops, each with the time it took
- ``requests()``    every ask as a card: owner, deadline, state, and what travels with it
- ``acceleration()``time to the next action and what the evidence unblocked — or None, which the UI
                    renders as an em dash. A saving that the record cannot support is never shown.
- ``inheritance()`` what the next incident with a learn signature starts with

Nothing here invents a number: each value is a timestamp difference or a count of stored rows, and
the tests compare the rendered hero against the record it came from.
"""
import datetime as dt
import sqlite3

import collab
import journey
import runclock

DB = "data/ops.db"

SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

# A request without a stated deadline gets the default response expectation. It is a product
# default, not a promise, and the card says which one it used.
DEFAULT_DEADLINE_MIN = 30

DATA_TEAMS = {"Data Platform", "Data Engineer", "Data Owner", "Finance Data",
              "Analytics Engineering", "Data Consumer"}

STATE_LABEL = {"assigned": "sent", "accepted": "acknowledged", "done": "answered",
               "reopened": "reopened"}
STATE_TONE = {"sent": "#64748b", "acknowledged": "#0f766e", "answered": "#166534",
              "overdue": "#b91c1c", "reopened": "#b45309"}


# ---------------------------------------------------------------- time helpers
def _dt(value):
    try:
        return dt.datetime.fromisoformat(str(value))
    except Exception:
        return None


def _now():
    return runclock.now()


def minutes_between(start, end=None):
    """Whole minutes from `start` to `end` (now by default), or None when start is unknown."""
    a = _dt(start)
    if a is None:
        return None
    b = _dt(end) if end is not None else _now()
    if b is None:
        return None
    return max(0, int((b - a).total_seconds() / 60))


def fmt_minutes(minutes):
    """53m · 1h 04m · 2d 3h — short, and the same everywhere."""
    if minutes is None:
        return "—"
    m = int(minutes)
    if m < 60:
        return f"{m}m"
    if m < 60 * 24:
        return f"{m // 60}h {m % 60:02d}m"
    return f"{m // (60 * 24)}d {(m % (60 * 24)) // 60}h"


def _con():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _closed_at(inc):
    """The moment the clock stopped for a closed incident — a closed incident's clock must not run
    on to now, or a six-day-old closure reads as 'held 6d'."""
    if (inc.get("status") or "").lower() != "closed":
        return None
    rows = _rows("SELECT closed_at, updated_at FROM resolution_state WHERE ref_id=?", (inc["id"],))
    if rows:
        return rows[0].get("closed_at") or rows[0].get("updated_at")
    return None


def _rows(sql, params=()):
    con = _con()
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()
    return rows


# ---------------------------------------------------------------- the record behind the claims
def origin(inc):
    """The service or data product the incident was raised on."""
    if inc.get("service_id"):
        r = _rows("SELECT name, type FROM services WHERE id=?", (inc["service_id"],))
        return {"label": r[0]["name"] if r else inc["service_id"], "kind": "app", "domain": "App"}
    if inc.get("dataset_id"):
        r = _rows("SELECT name FROM dop_datasets WHERE id=?", (inc["dataset_id"],))
        return {"label": r[0]["name"] if r else inc["dataset_id"], "kind": "data", "domain": "Data"}
    return {"label": inc["id"], "kind": "incident", "domain": "IT Ops"}


def impact(inc):
    """Business impact in one line — what a person needs when they are asked to help."""
    if inc.get("service_id"):
        edges = _rows("SELECT src, rel, dst FROM edges")
        biz = next((e["src"] for e in edges if e["dst"] == inc["service_id"]
                    and e["rel"] == "supported_by"), None)
        if not biz:
            return {"text": "no business service mapped", "service": None, "kpi": None}
        svc = _rows("SELECT name FROM services WHERE id=?", (biz,))
        kpi = _rows("SELECT metric, current, baseline, unit FROM kpis WHERE business_service=?", (biz,))
        name = svc[0]["name"] if svc else biz
        if kpi:
            k = kpi[0]
            return {"text": f'{name} · {k["metric"].replace("_pct", "").replace("_", " ")} '
                            f'{k["current"]:g}{k["unit"]} vs {k["baseline"]:g}{k["unit"]}',
                    "service": name, "kpi": k}
        return {"text": name, "service": name, "kpi": None}
    if inc.get("dataset_id"):
        r = _rows("SELECT name FROM dop_datasets WHERE id=?", (inc["dataset_id"],))
        name = r[0]["name"] if r else inc["dataset_id"]
        f = journey.freshness(inc["dataset_id"])
        if f:
            return {"text": f'{name} · freshness {f["lag_min"]}m vs {f["sla_min"]}m SLA',
                    "service": name, "kpi": None}
        return {"text": name, "service": name, "kpi": None}
    return {"text": "—", "service": None, "kpi": None}


def evidence(inc, limit=2):
    """The observed facts that travel with an ask — recorded alerts and defects, newest last."""
    rows = _rows("SELECT kind, detail, ts FROM timeline WHERE ref_id=? "
                 "AND kind IN ('alert','ticket','repair') ORDER BY ts", (inc["id"],))
    return [r["detail"] for r in rows][-limit:]


def _asks(ref):
    """Open + closed requests on one incident, oldest first."""
    return sorted(collab.delegations(ref), key=lambda d: d.get("ts") or "")


def deadline_minutes(d):
    """The deadline stated in the ask ('expected in 30 min'), else the product default."""
    text = str(d.get("action") or "")
    import re
    m = re.search(r"expected in (\d+) min", text)
    return int(m.group(1)) if m else DEFAULT_DEADLINE_MIN


# ---------------------------------------------------------------- hero: the first three seconds
def waiting(inc):
    """Who holds the work, and for how long. The same request the cards below show first."""
    open_asks = [d for d in _asks(inc["id"]) if d.get("status") != "done" and d.get("sent_at")]
    if not open_asks:
        # a request recorded but never handed over is waiting on *you*, not on its owner
        return {"who": None, "minutes": None, "text": "No open request", "empty": True,
                "note": "nobody is holding it — ask someone"}
    d = min(open_asks, key=lambda x: x.get("ts") or "")
    m = collab.age_minutes(d)
    limit = deadline_minutes(d)
    return {"who": d["to_"], "minutes": m, "text": f'Waiting {fmt_minutes(m)} · {d["to_"]}',
            "empty": False, "overdue": m > limit, "deadline_min": limit, "request": d}


def sla(inc):
    """The customer SLA clock — priority target hours from the incident's own created_at."""
    if (inc.get("status") or "").lower() == "closed":
        return {"text": "closed", "remaining_min": None, "target_hours": None,
                "elapsed_hours": None, "closed": True, "breached": False}
    target = SLA_HOURS.get(inc.get("priority"), 8)
    created = _dt(inc.get("created_at"))
    elapsed_h = ((_now() - created).total_seconds() / 3600) if created else 0.0
    rem = target - elapsed_h
    if rem <= 0:
        text = "BREACHED"
    else:
        text = f"{int(rem)}h {int((rem % 1) * 60)}m left"
    return {"text": text, "remaining_min": rem * 60, "target_hours": target,
            "elapsed_hours": elapsed_h, "closed": False, "breached": rem <= 0}


def chain(inc):
    """The handoff path as hops: origin → whoever holds it now → the upstream incident.

    Each hop carries the time that hop has taken, so a handoff is something you can see rather
    than a badge. The current holder is the open request's recipient (else the owning team)."""
    origin_node = origin(inc)
    created = inc.get("created_at")
    asks = _asks(inc["id"])
    open_asks = [d for d in asks if d.get("status") != "done"]
    holder = min(open_asks, key=lambda x: x.get("ts") or "") if open_asks else None
    first_ask = asks[0] if asks else None
    nodes = []

    end = _closed_at(inc)
    held = minutes_between(created, first_ask["ts"] if first_ask else end)
    stale = None
    if inc.get("service_id") and (inc.get("status") or "").lower() != "closed":
        ds = journey.stale_dataset(inc["id"])
        f = journey.freshness(ds) if ds else None
        if f and f["breach"]:
            stale = f'{f["lag_min"]}m stale · {f["sla_min"]}m SLA'
    nodes.append({"id": "origin", "label": origin_node["label"], "kind": origin_node["domain"],
                  "domain": origin_node["domain"], "holder": False,
                  "since": created, "elapsed_min": held,
                  "clock": f'{fmt_minutes(held)} before handoff' if first_ask
                  else f'held {fmt_minutes(held)}',
                  "hint": "detected here", "stale": stale})

    if holder:
        dom = "Data Platform" if holder["to_"] in DATA_TEAMS else "IT Ops"
        nodes.append({"id": f'team:{holder["to_"]}', "label": holder["to_"], "kind": "team",
                      "domain": dom, "holder": True, "since": holder["ts"],
                      "elapsed_min": minutes_between(holder["ts"], end),
                      # the wait itself is the hero's fact; the chip only says who holds it now
                      "clock": "current holder",
                      "hint": "holds the work now"})
    else:
        owner = inc.get("owner_team")
        dom = "Data Platform" if owner in DATA_TEAMS else "IT Ops"
        nodes.append({"id": f"team:{owner}", "label": owner or "unassigned", "kind": "team",
                      "domain": dom, "holder": True, "since": created,
                      "elapsed_min": minutes_between(created, end),
                      "clock": f'owns it {fmt_minutes(minutes_between(created, end))}',
                      "hint": "owns it"})

    corr = journey.correlation_for(inc["id"])
    if corr:
        other_id = corr["other_id"]
        row = _rows("SELECT created_at FROM incidents WHERE id=? UNION ALL "
                    "SELECT created_at FROM dop_incidents WHERE id=?", (other_id, other_id))
        since = row[0]["created_at"] if row else None
        nodes.append({"id": other_id, "label": other_id,
                      "kind": "DataOps" if corr["other_domain"] == "DataOps" else "IT Ops",
                      "domain": "DataOps" if corr["other_domain"] == "DataOps" else "IT Ops",
                      "holder": False, "since": since,
                      "elapsed_min": minutes_between(since, end),
                      "clock": f'open {fmt_minutes(minutes_between(since, end))}',
                      "hint": "upstream cause", "stale": None})
    return nodes


def cross(inc):
    """Domains touched and handoffs made — the third hero fact, counted from the chain and rows."""
    nodes = chain(inc)
    domains = len({n["domain"] for n in nodes})
    handoffs = len(_asks(inc["id"]))
    if handoffs:
        tail = f'{handoffs} handoff{"s" if handoffs != 1 else ""}'
    else:
        tail = "no handoff" if (inc.get("status") or "").lower() == "closed" else "no handoff yet"
    return {"domains": domains, "handoffs": handoffs, "text": f"{domains} domains · {tail}",
            "nodes": nodes}


def hero(inc):
    """The three facts, in order, with the record each came from."""
    w, s, c = waiting(inc), sla(inc), cross(inc)
    return {
        "waiting": w, "sla": s, "cross": c,
        "facts": [
            {"label": "Open request", "value": w["text"], "note":
                (fmt_minutes(w["deadline_min"]) + " deadline") if w.get("overdue")
                else (("closed — no request open" if s["closed"]
                       else "nobody is holding it — ask someone") if w["empty"]
                      else f'deadline {fmt_minutes(w["deadline_min"])}'),
             "tone": "#b91c1c" if w.get("overdue") else ("#94a3b8" if w["empty"] else "#0f172a"),
             "empty": w["empty"]},
            {"label": "SLA remaining", "value": s["text"],
             "tone": "#b91c1c" if s["breached"] else "#0f172a",
             "note": "customer clock" if not s["closed"] else "closed on the verified record",
             "empty": s["closed"]},
            {"label": "Cross-domain", "value": c["text"], "tone": "#0f172a",
             "note": " · ".join(n["label"] for n in c["nodes"]), "empty": False},
        ],
    }


# ---------------------------------------------------------------- collaboration: the ask as a card
def requests(ref):
    """Every ask as a card. The state is derived from the recorded transitions, never assumed."""
    out = []
    for d in _asks(ref):
        age = collab.age_minutes(d)
        limit = deadline_minutes(d)
        status = str(d.get("status") or "assigned").lower()
        sent_at = d.get("sent_at")
        state = "not sent" if not sent_at else STATE_LABEL.get(status, status)
        # a request nobody has received cannot be late: the clock starts when it is sent
        overdue = status != "done" and bool(sent_at) and age > limit
        if overdue:
            state = "overdue"
        asked = d.get("action") or ""
        out.append({
            "id": d["id"], "owner": d["to_"], "ask": asked,
            "ask_short": asked.split(" · expected in")[0],
            "state": state,
            "status": status, "age_min": age, "deadline_min": limit, "overdue": overdue,
            "stage": d.get("stage") or "—", "channel": d.get("channel") or "App",
            "asked_by": d.get("frm") or "—", "since": d.get("ts"),
            "over_by": max(0, age - limit) if overdue else 0,
            "sent_at": sent_at,            # NULL: recorded but never handed over (NOT SENT)
            "unsent": not sent_at,
            "travels": d.get("travels") or "",
            "actor": d.get("actor") or d.get("frm") or "—",
            "changed_at": d.get("changed_at") or d.get("ts"),
            "delivered": bool(sent_at),    # no connector is configured; SENT is a recorded send
            "tone": STATE_TONE.get(state, "#64748b"),
        })
    return out



# ---------------------------------------------------------------- acceleration: measured, or a dash
def acceleration(inc):
    """Two measured durations, each with the record that supports it.

    time to next action   — incident raised → first recorded action (a handoff or a repair)
    unblocked by evidence — the oldest open request → the first evidence recorded after it
    None means the record cannot support the number; the UI shows an em dash.
    """
    created = inc.get("created_at")
    asks = _asks(inc["id"])
    timeline = _rows("SELECT kind, detail, ts FROM timeline WHERE ref_id=? ORDER BY ts", (inc["id"],))
    repairs = [t for t in timeline if t["kind"] == "repair"]

    actions = [{"ts": d["ts"], "what": f'handed to {d["to_"]}', "kind": "handoff"} for d in asks]
    actions += [{"ts": t["ts"], "what": t["detail"], "kind": "repair"} for t in repairs]
    actions = [a for a in actions if _dt(a["ts"])]
    actions.sort(key=lambda a: a["ts"])
    first = actions[0] if actions else None
    tta = minutes_between(created, first["ts"]) if first else None

    open_asks = [d for d in asks if d.get("status") != "done"]
    holder = min(open_asks, key=lambda x: x.get("ts") or "") if open_asks else None
    unblocked, why = None, None
    if holder:
        after = [t for t in timeline
                 if t["kind"] in ("alert", "ticket", "repair") and (_dt(t["ts"]) or _now())
                 > (_dt(holder["ts"]) or _now())]
        if after:
            unblocked = minutes_between(holder["ts"], after[0]["ts"])
            why = after[0]["detail"]

    return {
        "time_to_next_action_min": tta,
        "time_to_next_action_what": first["what"] if first else None,
        "unblocked_by_evidence_min": unblocked,
        "unblocked_by_evidence_what": why,
        "holder": holder["to_"] if holder else None,
    }


# ---------------------------------------------------------------- learn: inheritance
def inheritance(rec):
    """What the next incident with this signature starts with: the cause and the runbook."""
    return {
        "signature": rec.get("signature") or "unclassified",
        "root_cause": rec.get("root_cause") or "—",
        "runbook": list(rec.get("steps") or []),
        "ref": rec.get("ref"),
        "outcome": rec.get("outcome"),
        "reused_from": rec.get("reused_from"),
    }
