#!/usr/bin/env python3
"""Developer context — from a Jira ticket to the full operational evidence bundle.
Answers: 'why does this ticket exist, what's impacted, what changed, what do I fix, how is it verified?'"""
import datetime as dt
import duckdb
import engine as E

DB_HIST = "data/history.duckdb"
import story  # one definition of the SLA clock
SLA_HOURS = story.SLA_HOURS


def _kpi_now():
    try:
        con = duckdb.connect(DB_HIST)
        v = con.execute("SELECT value FROM kpi WHERE scenario='current' ORDER BY ts DESC LIMIT 1").fetchone()[0]
        con.close()
        return round(float(v), 1)
    except Exception:
        return None


def _sla(inc):
    try:
        created = dt.datetime.fromisoformat(inc["created_at"])
        hours = SLA_HOURS.get(inc["priority"], 8)
        remaining = hours - (dt.datetime.now() - created).total_seconds() / 3600
        if remaining <= 0:
            return "BREACHED", round(remaining, 1)
        return f"{int(remaining)}h {int((remaining % 1) * 60)}m remaining", round(remaining, 1)
    except Exception:
        return "unknown", None


def context(ticket_id):
    services, edges, incidents, changes, metrics, G = E.load()
    tickets = E.load_tickets()
    ticket = next((t for t in tickets if t["id"] == ticket_id), None)
    if not ticket:
        return None
    inc = next((i for i in incidents if i["id"] == ticket["incident_id"]), None)
    sid = ticket["service_id"]
    chain = E.impact_chain(G, sid)
    biz = E.business_service(G, chain, services)
    downstream = sorted(E.impacted(G, sid) - set(chain) - {sid}) if inc else []
    causes = E.causes(inc, G, changes, metrics, services) if inc else []
    rec = E.recommend(inc, causes) if inc else None
    similar = E.similar(incidents, inc, 2) if inc else []
    kpi = _kpi_now()
    krow = next((k for k in E.load_kpis() if k["business_service"] == biz), None) if biz else None
    sla, sla_h = (_sla(inc) if inc else ("n/a", None))
    change = next((c for c in changes if c["service_id"] == sid), None)

    evidence = []
    if inc:
        evidence.append(f'[INC] {inc["id"]} · {inc["title"]} · {inc["priority"]}/{inc["status"]} · {inc["created_at"]}')
    evidence.append(f'[JIRA] {ticket["id"]} · {ticket["title"]} · {ticket["status"]} · {ticket["assignee"]}')
    if change:
        evidence.append(f'[CHG] {change["id"]} · {change["service_id"]} · {change["description"]}')
    for m in metrics:
        if m["service_id"] in E.impacted(G, sid) and m["value"] > m["threshold"]:
            evidence.append(f'[METRIC] {m["service_id"]} {m["metric"]}={m["value"]:.0f} (threshold {m["threshold"]:.0f})')
    if kpi is not None:
        evidence.append(f'[KPI] checkout_success_pct = {kpi}% (baseline 98.5%)')
    evidence.append(f'[GRAPH] {" → ".join(services[n]["name"] for n in reversed(chain))}')
    evidence += [f'[SIMILAR] {s}' for s in similar]

    bundle = {
        "ticket": ticket,
        "incident": inc,
        "service": services[sid]["name"],
        "business": services[biz]["name"] if biz else None,
        "path": " → ".join(services[n]["name"] for n in reversed(chain)),
        "downstream": [services[n]["name"] for n in downstream],
        "causes": [c["text"] for c in causes],
        "similar": similar,
        "kpi": kpi,
        "metric_name": (krow["metric"].replace("_", " ") if krow else "checkout success"),
        "baseline": (krow["baseline"] if krow else 98.5),
        "sla": sla,
        "change": change,
        "acceptance": ticket["acceptance"],
        "fix_hint": ticket["fix_hint"],
        "verify": (
            "Technical: p95 latency & error rate normal · Service: API latency recovers · "
            "Business: checkout success back to ~98.5%."
        ),
        "evidence": evidence,
        "record_link": f'{inc["id"] if inc else "—"} / {ticket["id"]}',
    }
    return bundle
