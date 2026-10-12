#!/usr/bin/env python3
"""Deterministic NLG composer — turns the evidence into fluent, persona-aware prose.
No LLM, no key: rule-based narrative with inline citations, confidence and 'so what / now what'."""


def _pick(options, seed):
    idx = sum(ord(c) for c in str(seed)) % len(options)
    return options[idx]


def _confidence(n):
    if n >= 8:
        return "high"
    if n >= 4:
        return "medium"
    return "low"


def narrative(f, intent="status", persona=None):
    """f = facts dict; returns a written narrative string with inline citations."""
    svc = f["subject"]
    open_ = f["open"]
    pri, status = f["priority"], f["status"]
    causes = f.get("causes") or []
    rec = f.get("rec")
    similar = f.get("similar") or []
    biz, kpi, path, sla = f.get("business"), f.get("kpi"), f.get("path"), f.get("sla")
    cite = f.get("cite", "")
    conf = _confidence(f.get("n_evidence", 0))
    s = {}

    # headline
    s["headline"] = (f'**{svc} — AT RISK ({pri}, {status}).**' if open_
                     else f'{svc} — steady ({status}).')

    # cause
    if causes:
        lead = _pick(["The operational picture points to", "The evidence points to",
                      "The most likely driver is", "RCA over the dependency graph shows"], svc)
        s["cause"] = f'{lead} {causes[0]}' + (f', with {len(causes)-1} further signal(s).'
                                              if len(causes) > 1 else '.')
    else:
        s["cause"] = "No change or metric breach is linked to it yet."

    s["path"] = f'Dependency path: {path}.'

    if biz and kpi is not None:
        mn = f.get("metric_name", "checkout success")
        base = f.get("baseline", 98.5)
        s["impact"] = (f'Business impact: **{biz}** — {mn} is **{kpi}%** against a {base}% baseline, '
                       f'so this is customer-impacting.')
    elif biz:
        s["impact"] = f'Business impact: **{biz}** (downstream of the affected service).'

    if rec:
        s["action"] = (f'Next actor is **{rec["actor"]}**; the recommended action is {rec["action"]} '
                       f'(gate: {rec["mode"]}{cite}).')
    if similar:
        s["precedent"] = "Precedent: " + "; ".join(similar) + "."
    if sla:
        s["sla"] = f'SLA: {sla}.'
    s["confidence"] = f'Confidence: {conf} ({f.get("n_evidence", 0)} evidence items).'

    # so what / now what
    sowhat = "customer-visible impact is live" if (biz and open_) else "impact is contained"
    nowwhat = rec["action"] if rec else "continue monitoring"
    s["sowhat"] = f'**So what:** {sowhat}. **Now what:** {nowwhat}'

    order = {
        None:        ["headline", "cause", "path", "impact", "action", "precedent", "sla", "confidence", "sowhat"],
        "CSM":       ["headline", "impact", "cause", "action", "sowhat", "confidence"],
        "L1 Engineer": ["headline", "action", "sla", "cause", "impact"],
        "L2 / L3 Engineer": ["headline", "cause", "path", "impact", "action", "precedent", "confidence"],
        "Incident Manager": ["headline", "sla", "action", "impact", "precedent", "sowhat"],
        "Developer": ["headline", "cause", "path", "impact", "action", "confidence"],
    }.get(persona, ["headline", "cause", "path", "impact", "action", "precedent", "sla", "confidence", "sowhat"])

    # intent emphasis — make sure the asked-about sentence is present and near the top
    key_for = {"cause": "cause", "who": "action", "impact": "impact",
               "sla": "sla", "recur": "precedent", "action": "action"}
    k = key_for.get(intent)
    if k and k in s:
        head = ["headline"] if "headline" in order else []
        order = head + [k] + [x for x in order if x not in ("headline", k)]

    return " ".join(s[x] for x in order if x in s)
