#!/usr/bin/env python3
"""Who's on it — a static, per-incident agent definition, rendered against the live record.

There is no agent runtime here and no model call. `agents.json` holds the narrative — the routing
decision, which specialist acted, the draft ask and the autonomy rung — and every *number* in the
panel is computed from the incident record at render time (story + journey + the RCA leads). That
is the condition: the panel may never contradict the record it sits on. If the record changes, the
numbers change with it; if an incident is not defined, the panel says so and shows nothing invented.
"""
import json
import os
import pathlib
import re

import journey
import story

PATH = os.environ.get("RI_AGENTS", str(pathlib.Path(__file__).with_name("agents.json")))

RUNGS = ["suggest", "draft", "act"]

# A signal's numeric weight is a *display* of the recorded basis and confidence, defined once here.
# observed signals are what the record saw; inferred ones are hypotheses, and a medium-confidence
# inference is 0.72 — the number the panel shows for the ledger link on INC-8841.
SIGNAL_SCORE = {"observed": {"high": 0.95, "medium": 0.9, "low": 0.85},
                "inferred": {"high": 0.85, "medium": 0.72, "low": 0.55}}


def load():
    try:
        return json.loads(pathlib.Path(PATH).read_text())
    except Exception:
        return {"incidents": {}, "agents": []}


def defined(ref):
    return ref in (load().get("incidents") or {})


def _rows(sql, params=()):
    return story._rows(sql, params)


def facts(inc):
    """Every number the panel is allowed to print, from the record — not from the JSON file."""
    ref = inc["id"]
    w = story.waiting(inc)
    s = story.sla(inc)
    c = story.cross(inc)
    out = {
        "wait": story.fmt_minutes(w["minutes"]) if not w["empty"] else "—",
        "holder": w["who"] or inc.get("owner_team") or "unassigned",
        "sla": s["text"],
        "domains": c["domains"],
        "handoffs": c["handoffs"],
        "owner": inc.get("owner_team") or "unassigned",
        "stage": journey.lifecycle_stage(inc),
        "impact": story.impact(inc)["text"],
        "evidence": " · ".join(story.evidence(inc)) or "no evidence recorded",
        "open_requests": w["text"] if not w["empty"] else "No open request",
    }
    ds = inc.get("dataset_id") or journey.stale_dataset(ref)
    f = journey.freshness(ds) if ds else None
    if f:
        out["freshness"] = f'{f["lag_min"]}m vs {f["sla_min"]}m SLA'
    else:
        out["freshness"] = "no freshness record"
    corr = journey.correlation_for(ref)
    out["upstream"] = (f'{corr["other_id"]} ({corr["other_domain"]}) owns the shared cause'
                       if corr else "no upstream incident linked")
    metric = _breaching_metric(inc)
    out["error_rate"] = metric or "no metric breach recorded"
    out["leads"] = _lead_counts(inc)
    out["signal"] = _signal(ref)
    return out


def _breaching_metric(inc):
    if not inc.get("service_id"):
        return None
    rows = _rows("SELECT metric, value, threshold FROM metrics WHERE service_id=? "
                 "AND value > threshold ORDER BY value / threshold DESC LIMIT 1",
                 (inc["service_id"],))
    if not rows:
        return None
    m = rows[0]
    unit = "%" if "pct" in m["metric"] or "rate" in m["metric"] else ""
    label = m["metric"].replace("_pct", "").replace("_", " ")
    return f'{label} {m["value"]:g}{unit} vs {m["threshold"]:g}{unit}'


def _lead_counts(inc):
    """Signals reviewed, leads ranked, low-confidence leads set aside — all from the thread.

    reviewed = signal rows on this incident; ranked = RCA leads the ranking produced; rejected =
    leads whose recorded confidence is low (set aside, not deleted)."""
    reviewed = len(_rows("SELECT id FROM thread_edges WHERE thread_ref=?", (inc["id"],)))
    leads = []
    try:
        if inc["id"].startswith("DOP"):
            import dataops_engine as DE
            leads = DE.causes(inc, DE.load())
        else:
            import engine as E
            services, edges, incidents, changes, metrics, G = E.load()
            leads = E.causes(inc, G, changes, metrics, services)
    except Exception:
        leads = []
    low = sum(1 for h in leads if str(h.get("confidence") or "").lower() == "low")
    return {"reviewed": reviewed, "ranked": len(leads), "rejected": low}


def _signal(ref):
    """The strongest *inferred* link on the thread, as the record states it, with its weight."""
    rows = _rows("SELECT src, dst, kind, confidence FROM thread_edges WHERE thread_ref=? "
                 "ORDER BY CASE kind WHEN 'inferred' THEN 0 ELSE 1 END, "
                 "CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END LIMIT 1", (ref,))
    if not rows:
        return {"label": "no signal recorded", "score": None, "basis": None}
    r = rows[0]
    kind = (r["kind"] or "inferred").lower()
    conf = (r["confidence"] or "low").lower()
    return {"label": f'{r["src"]} → {r["dst"]}', "score": SIGNAL_SCORE.get(kind, {}).get(conf),
            "basis": kind}


def panel(inc):
    """The definition for this incident, filled from the record. None when undefined."""
    block = (load().get("incidents") or {}).get(inc["id"])
    if not block:
        return None
    f = facts(inc)
    return {
        "ref": inc["id"],
        "orchestrator": {"decision": block["orchestrator"]["decision"],
                         "facts": [{"key": k, "text": _FACT_TEXT[k].format(**f)} if k in _FACT_TEXT
                                   else {"key": k, "text": str(f.get(k) or "—")}
                                   for k in block["orchestrator"].get("facts", [])]},
        "specialist": {"agent": block["specialist"]["agent"],
                       "did": block["specialist"]["did"],
                       "reviewed": f["leads"]["reviewed"],
                       "ranked": f["leads"]["ranked"],
                       "rejected": f["leads"]["rejected"],
                       "signal": f["signal"]},
        "handoff": {"to": block["handoff"]["to"], "ask": block["handoff"]["ask"],
                    "stage": f["stage"], "impact": f["impact"], "evidence": f["evidence"],
                    "delivered": False},
        "rung": block.get("rung", "suggest"),
        "facts": f,
    }


_FACT_TEXT = {
    "freshness": "freshness {freshness}",
    "error_rate": "{error_rate}",
    "upstream": "{upstream}",
    "sla": "SLA {sla}",
    "wait": "waiting {wait} on {holder}",
    "domains": "{domains} domains · {handoffs} handoffs",
    "owner": "owner {owner}",
}


def agents():
    """The six rows the Agents page shows: one live, five design."""
    return load().get("agents") or []
