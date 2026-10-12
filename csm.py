#!/usr/bin/env python3
"""CSM Assistant — answers 'what's the status of …?' with an evidence-led narrative.
Retrieval + intent over the same governed graph. No LLM required."""
import duckdb
import engine as E

DB_HIST = "data/history.duckdb"
KEYWORDS = {"payment": "its_payment_api", "checkout": "app_checkout",
            "database": "db_payments", "db": "db_payments", "api": "its_payment_api"}


def _target(q, services, incidents):
    ql = q.lower()
    for i in incidents:
        if i["id"].lower() in ql:
            return "incident", i
    for sid, s in services.items():
        if s["name"].lower() in ql:
            return "service", sid
    for k, v in KEYWORDS.items():
        if k in ql:
            return "service", v
    # default: most recent open incident
    open_ = [i for i in incidents if i["status"] == "open"]
    if open_:
        return "incident", sorted(open_, key=lambda i: i["created_at"], reverse=True)[0]
    return None, None


def _intent(q):
    ql = q.lower()
    if any(w in ql for w in ["impact", "business", "customer", "revenue", "kpi", "checkout success"]):
        return "impact"
    if any(w in ql for w in ["why", "cause", "root", "reason", "happening"]):
        return "cause"
    if any(w in ql for w in ["who", "owner", "next actor", "working", "assign", "team"]):
        return "who"
    if any(w in ql for w in ["sla", "risk", "breach", "late"]):
        return "sla"
    if any(w in ql for w in ["again", "recur", "repeat", "similar", "precedent", "before"]):
        return "recur"
    if any(w in ql for w in ["doing", "action", "fix", "resolve", "next step", "recommend"]):
        return "action"
    return "status"


def _latest_incident(sid, incidents, G):
    scope = E.impacted(G, sid)
    open_ = [i for i in incidents if i["service_id"] in scope and i["status"] == "open"]
    pool = open_ or [i for i in incidents if i["service_id"] in scope]
    return sorted(pool, key=lambda i: i["created_at"], reverse=True)[0] if pool else None


def _kpi_now():
    try:
        con = duckdb.connect(DB_HIST)
        v = con.execute("SELECT value FROM kpi WHERE scenario='current' ORDER BY ts DESC LIMIT 1").fetchone()[0]
        con.close()
        return round(float(v), 1)
    except Exception:
        return None


def answer(question):
    services, edges, incidents, changes, metrics, G = E.load()
    kind, tgt = _target(question, services, incidents)
    intent = _intent(question)
    if tgt is None:
        return {"answer": "I couldn't map that to a service or incident. Try “status of Payments”, "
                          "“why is checkout slow?”, or “SLA risk on INC-8841”.",
                "evidence": [], "intent": intent, "target": None}

    inc = tgt if kind == "incident" else _latest_incident(tgt, incidents, G)
    sid = inc["service_id"] if inc else tgt
    chain = E.impact_chain(G, sid)
    biz = E.business_service(G, chain, services)
    causes = E.causes(inc, G, changes, metrics, services) if inc else []
    rec = E.recommend(inc, causes) if inc else None
    kpi = _kpi_now()
    similar = E.similar(incidents, inc, 2) if inc else []
    story = " → ".join(services[n]["name"] for n in reversed(chain))
    cause_txt = "; ".join(c["text"] for c in causes) if causes else "no change or metric breach found"

    if inc and inc["status"] == "open":
        head = f'**{services[biz]["name"] if biz else services[sid]["name"]} — AT RISK.**'
    elif inc:
        head = f'{services[biz]["name"] if biz else services[sid]["name"]} — steady.'
    else:
        head = f'{services[sid]["name"]} — no incident found.'

    parts = [head]
    if inc:
        parts.append(f'{inc["title"]} ({inc["id"]}, {inc["priority"]}, {inc["status"]}).')
    parts.append(f'Service path: {story}.')
    if biz and kpi is not None:
        parts.append(f'Business impact: **{services[biz]["name"]}** — checkout success {kpi}% (from ~98.5%).')
    if intent in ("status", "cause"):
        parts.append(f'Likely cause / blockers: {cause_txt}.')
    if intent in ("status", "who") and rec:
        parts.append(f'Next actor: **{rec["actor"]}**.')
    if intent in ("status", "sla"):
        parts.append('SLA risk: **elevated** — customer-impacting and still open.'
                     if (inc and inc["status"] == "open") else 'SLA risk: low.')
    if intent in ("status", "recur") and similar:
        parts.append('Precedent: ' + "; ".join(similar) + '.')
    if rec:
        parts.append(f'Recommended action ({rec["mode"]}): {rec["action"]}')

    evidence = []
    if inc:
        evidence.append(f'[INC] {inc["id"]} · {inc["title"]} · {inc["priority"]}/{inc["status"]} · {inc["created_at"]}')
    scope = E.impacted(G, sid)
    for ch in changes:
        if ch["service_id"] in scope:
            evidence.append(f'[CHG] {ch["id"]} · {ch["service_id"]} · {ch["description"]} · {ch["deployed_at"]}')
    for m in metrics:
        if m["service_id"] in scope and m["value"] > m["threshold"]:
            evidence.append(f'[METRIC] {m["service_id"]} {m["metric"]}={m["value"]:.0f} (threshold {m["threshold"]:.0f})')
    if kpi is not None:
        evidence.append(f'[KPI] checkout_success_pct = {kpi}% (baseline 98.5%)')
    evidence.append(f'[GRAPH] {story}')
    evidence += [f'[SIMILAR] {s}' for s in similar]

    return {"answer": " ".join(parts), "evidence": evidence, "intent": intent, "target": sid}
