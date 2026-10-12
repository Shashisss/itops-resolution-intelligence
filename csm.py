#!/usr/bin/env python3
"""CSM Assistant — evidence-led, persona-aware answers (deterministic NLG, no LLM required)."""
import datetime as dt
import duckdb
import engine as E
import nlg

DB_HIST = "data/history.duckdb"
KEYWORDS = {"payment": "its_payment_api", "checkout": "app_checkout",
            "database": "db_payments", "db": "db_payments", "api": "its_payment_api"}
SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}


def _sla(inc):
    try:
        created = dt.datetime.fromisoformat(inc["created_at"])
        hrs = SLA_HOURS.get(inc["priority"], 8) - (dt.datetime.now() - created).total_seconds() / 3600
        return ("BREACHED" if hrs <= 0 else f"{int(hrs)}h {int((hrs % 1) * 60)}m left"), hrs
    except Exception:
        return "n/a", None


def customer_narrative(sid):
    """Customer-safe update drafted from the same evidence (validate/edit before sending)."""
    services, edges, incidents, changes, metrics, G = E.load()
    chain = E.impact_chain(G, sid)
    biz = E.business_service(G, chain, services)
    kpi = _kpi_now()
    svc = services[biz]["name"] if biz else services[sid]["name"]
    impact = (f"a small share of transactions (around {max(1, round(100 - kpi))}%) may be slow or fail"
              if kpi is not None else "some transactions may be slow or fail")
    return "\n".join([
        f"Customer update — {svc}",
        "",
        f"We are aware of intermittent issues affecting {svc}, and our teams are actively working to resolve them.",
        f"Impact: {impact}. There is no data loss or security impact.",
        "What we are doing: we have identified the likely contributor and are applying a corrective change "
        "under our standard change control and validation.",
        "Next update: within 60 minutes — or sooner if service returns to normal.",
        "We will confirm once performance is fully restored.",
    ])


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
    open_ = [i for i in incidents if i["status"] == "open"]
    if open_:
        return "incident", sorted(open_, key=lambda i: i["created_at"], reverse=True)[0]
    return None, None


def _intent(q):
    ql = q.lower()
    if any(w in ql for w in ["tell the customer", "customer update", "say to the customer",
                             "tell my customer", "customer message", "update for the customer"]):
        return "customer"
    if any(w in ql for w in ["impact", "business", "revenue", "kpi", "checkout success"]):
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


def _kpi_now(metric="checkout_success_pct"):
    try:
        con = duckdb.connect(DB_HIST)
        v = con.execute("SELECT value FROM kpi WHERE scenario='current' AND metric=? ORDER BY ts DESC LIMIT 1",
                        [metric]).fetchone()[0]
        con.close()
        return round(float(v), 1)
    except Exception:
        return None


def suggestions(inc, services):
    """Context-aware suggested questions for the selected incident."""
    svc = services[inc["service_id"]]["name"]
    iid = inc["id"]
    return [
        f"What is the status of {svc}?",
        f"Why is {svc} impacted?",
        f"Who is working on {iid}?",
        f"What is the business impact of {iid}?",
        f"Is there an SLA risk on {svc}?",
        "Will this recur?",
        "What should I tell the customer?",
    ]


def answer(question, persona=None):
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
    # Business KPI is scenario-specific: only used when one is mapped to this business service.
    krow = next((k for k in E.load_kpis() if k["business_service"] == biz), None) if biz else None
    metric_name = krow["metric"].replace("_", " ") if krow else None
    baseline = krow["baseline"] if krow else None
    kpi = _kpi_now(krow["metric"]) if krow else None
    similar = E.similar(incidents, inc, 2) if inc else []
    story = " → ".join(services[n]["name"] for n in reversed(chain))
    sla_txt, _ = _sla(inc) if inc else ("n/a", None)
    scope = E.impacted(G, sid)
    change = next((c for c in changes if c["service_id"] in scope), None)

    # evidence ledger
    evidence = []
    if inc:
        evidence.append(f'[INC] {inc["id"]} · {inc["title"]} · {inc["priority"]}/{inc["status"]} · {inc["created_at"]}')
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

    if intent == "customer":
        text = customer_narrative(sid)
    else:
        cite = ""
        if inc:
            cite = f' — see {inc["id"]}' + (f', {change["id"]}' if change else '')
        facts = dict(subject=services[sid]["name"], open=bool(inc and inc["status"] == "open"),
                     priority=inc["priority"] if inc else "—", status=inc["status"] if inc else "—",
                     causes=[c["text"] for c in causes], rec=rec, similar=similar,
                     business=services[biz]["name"] if (biz and krow) else None, kpi=kpi, path=story,
                     sla=sla_txt, n_evidence=len(evidence), cite=cite,
                     metric_name=metric_name, baseline=baseline)
        text = nlg.narrative(facts, intent, persona)

    return {"answer": text, "evidence": evidence, "intent": intent, "target": sid, "persona": persona}
