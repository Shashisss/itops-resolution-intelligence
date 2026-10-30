#!/usr/bin/env python3
"""The incident screen as one HTML block (v109).

Streamlit containers fought each other: overlapping bands, clipped tiles, a tab strip on top of the
hero, duplicate keys in the overlay. This module renders the whole screen — header, four tiles, the
dependency graph, "what this means", the single action, six tabs and their panes — as one document,
generated from the record and embedded with `st.components.v1.html(..., height=768, scrolling=False)`.

Nothing here is a literal: every number comes from `story`, `journey`, `collab`, `learn` or the
tables those modules read. Tabs and the full view switch client-side, so clicking never reflows the
page and no Streamlit widget is created inside the incident area (so no key can collide).

The only server round-trip is an action: the buttons are real anchors carrying `?action=…`, which
`app.py` reads once, performs on the record, and clears.
"""
import datetime as dt
import html as _html
import json

import collab
import journey
import learn
import story

WEEK = dt.date.today().strftime("%d %b %Y")
TAB_NAMES = ["Timeline", "Requests", "Evidence & RCA", "Connections & audit",
             "Act & verify", "Learn"]


def esc(v):
    return _html.escape(str(v if v is not None else ""))


# ---------------------------------------------------------------- record → facts
def facts(inc):
    w, s, c = story.waiting(inc), story.sla(inc), story.cross(inc)
    ds = inc.get("dataset_id") or journey.stale_dataset(inc["id"])
    f = journey.freshness(ds) if ds else None
    kpi = story.impact(inc).get("kpi")
    corr = journey.correlation_for(inc["id"])
    asks = [d for d in collab.delegations(inc["id"]) if d.get("status") != "done"]
    oldest = min(asks, key=lambda d: d.get("ts") or "") if asks else None
    sig = story._rows("SELECT kind, confidence FROM thread_edges WHERE thread_ref=? AND kind='inferred' "
                      "ORDER BY CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END LIMIT 1",
                      (inc["id"],))
    score = None
    if sig:
        import agents
        score = agents.SIGNAL_SCORE.get("inferred", {}).get((sig[0]["confidence"] or "").lower())

    metric = _metric(inc)
    return {
        "id": inc["id"],
        "title": inc.get("title") or "",
        "priority": inc.get("priority") or "",
        "stage": journey.lifecycle_stage(inc),
        "clock": s["text"],
        "closed": (inc.get("status") or "").lower() == "closed",
        "holder": w["who"] or inc.get("owner_team") or "—",
        "wait_min": w["minutes"],
        "wait_txt": story.fmt_minutes(w["minutes"]) if not w["empty"] else "—",
        "overdue": bool(w.get("overdue")),
        "over_by": (w["minutes"] - w["deadline_min"]) if not w["empty"] and w.get("overdue") else 0,
        "no_holder": bool(w["empty"]),
        "metric": metric,
        "fresh": f,
        "kpi": kpi,
        "domains": c["domains"],
        "handoffs": c["handoffs"],
        "corr": corr,
        "score": score,
        "asked": oldest,
        "owns": inc.get("owner_team") or "—",
        "service": _service_name(inc),
        "dataset": (f["name"] if f else (inc.get("dataset_id") or "dataset")),
        "evidence": story.evidence(inc, limit=99),
        "verdict": journey.current_verdict(inc),
        "gate": journey.closure_state(inc),
        "next": journey.next_action(inc, journey.lifecycle_stage(inc)),
        "impact": story.impact(inc)["text"],
    }


def _metric(inc):
    if inc.get("service_id"):
        rows = story._rows("SELECT metric, value, threshold FROM metrics WHERE service_id=? "
                           "AND value > threshold ORDER BY value / threshold DESC LIMIT 1",
                           (inc["service_id"],))
        if rows:
            m = rows[0]
            unit = "%" if "pct" in m["metric"] or "rate" in m["metric"] else ""
            return {"label": m["metric"].replace("_pct", "").replace("_", " "),
                    "value": f'{m["value"]:g}{unit}', "threshold": f'{m["threshold"]:g}{unit}',
                    "ratio": (m["value"] / m["threshold"]) if m["threshold"] else 0}
    rows = story._rows("SELECT COUNT(*) AS n FROM dop_runs WHERE pipeline_id=? AND status != 'success'",
                       (inc.get("pipeline_id"),))
    n = rows[0]["n"] if rows else 0
    return {"label": "failed runs", "value": str(n), "threshold": "0", "ratio": float(n)}


def _service_name(inc):
    if inc.get("service_id"):
        rows = story._rows("SELECT name FROM services WHERE id=?", (inc["service_id"],))
        if rows:
            return rows[0]["name"]
    if inc.get("pipeline_id"):
        rows = story._rows("SELECT name FROM pipelines WHERE id=?", (inc["pipeline_id"],))
        if rows:
            return rows[0]["name"]
        return inc["pipeline_id"]
    return inc.get("dataset_id") or inc["id"]


# ---------------------------------------------------------------- fragments
def _header(F, queue):
    return f'''<div class="hdr">
  <div class="bc"><a class="back" href="?inc={esc(F["id"])}&action=back" target="_top">← All incidents</a>
    <span>Incidents / {esc(F["id"])}</span></div>
  <div class="row">
    <span class="t">{esc(F["title"])}</span>
    <span class="r">
      <span class="pill">{esc(F["priority"])}</span>
      <span class="pill">{esc(F["stage"])}</span>
      <span class="q">{esc(queue)}</span>
      <span class="clock">{esc(F["clock"])}</span>
    </span>
  </div>
</div>'''


def _tiles(F):
    m, f, kpi = F["metric"], F["fresh"], F["kpi"]
    wait_q = ("nobody is holding it" if F["no_holder"] else
              f'{F["wait_txt"]} · {F["over_by"]}m over deadline' if F["overdue"] else
              f'{F["wait_txt"]} · {story.DEFAULT_DEADLINE_MIN}m deadline')
    fresh_v = f'{f["lag_min"]}m' if f else "—"
    fresh_q = (f'SLA {f["sla_min"]}m — {max(1, f["lag_min"] // f["sla_min"])}x over'
               if f and f["lag_min"] >= f["sla_min"] else (f'SLA {f["sla_min"]}m' if f else "no record"))
    kpi_v = f'{kpi["current"]:g}{kpi["unit"]}' if kpi else "—"
    kpi_q = f'baseline {kpi["baseline"]:g}{kpi["unit"]}' if kpi else "no KPI mapped"
    return f'''<section class="tiles">
  <div class="tile"><div class="k">Waiting on</div><div class="v">{esc(F["holder"])}</div>
    <div class="q">{esc(wait_q)}</div></div>
  <div class="tile"><div class="k">{esc("Error rate" if F["metric"]["label"] == "error rate" else "Failed runs")}</div>
    <div class="v">{esc(m["value"])}</div><div class="q">vs {esc(m["threshold"])} threshold</div></div>
  <div class="tile"><div class="k">Data freshness</div><div class="v">{esc(fresh_v)}</div>
    <div class="q">{esc(fresh_q)}</div></div>
  <div class="tile"><div class="k">Checkout</div><div class="v">{esc(kpi_v)}</div>
    <div class="q">{esc(kpi_q)}</div></div>
</section>'''


def _graph(F):
    f, corr = F["fresh"], F["corr"]
    kpi = F["kpi"]
    kpi_txt = f'checkout {kpi["current"]:g}{kpi["unit"]}' if kpi else "—"
    conn = _conn_line(F["id"])
    return f'''<div class="card grow">
  <h2>Why this is happening</h2>
  <svg viewBox="0 0 800 200" preserveAspectRatio="xMidYMid meet" class="graph">
    <defs>
      <marker id="as" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
        <path d="M0,0 L7,3.5 L0,7 z" fill="#475569"/></marker>
      <marker id="ad" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
        <path d="M0,0 L7,3.5 L0,7 z" fill="#b45309"/></marker>
    </defs>
    <g font-size="11">
      <rect x="8" y="18" width="150" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>
      <text x="17" y="35" font-size="8.5" fill="#64748b">CHANGE</text>
      <text x="17" y="51" font-weight="650">core_ledger v4</text>

      <rect x="250" y="18" width="180" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>
      <text x="259" y="35" font-size="8.5" fill="#64748b">JOB</text>
      <text x="259" y="51" font-weight="650">payments_bronze_ingest</text>

      <rect x="60" y="132" width="150" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>
      <text x="69" y="149" font-size="8.5" fill="#64748b">INCIDENT</text>
      <text x="69" y="165" font-weight="650">{esc(corr["other_id"]) if corr else "—"}</text>

      <rect x="250" y="132" width="180" height="44" rx="8" fill="#fff" stroke="#fdba74"/>
      <text x="259" y="149" font-size="8.5" fill="#b45309">DATASET · STALE {f["lag_min"] if f else "—"}m</text>
      <text x="259" y="165" font-weight="650">{esc(F["dataset"])}</text>

      <rect x="480" y="132" width="180" height="44" rx="8" fill="#eef2ff" stroke="#4f46e5"/>
      <text x="489" y="149" font-size="8.5" fill="#3730a3">SERVICE · {"LIVE" if not F["closed"] else "CLOSED"}</text>
      <text x="489" y="165" font-weight="700">{esc(F["service"])}</text>

      <rect x="700" y="132" width="94" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>
      <text x="709" y="149" font-size="8.5" fill="#64748b">KPI</text>
      <text x="709" y="165" font-weight="650">{esc(kpi_txt)}</text>
    </g>
    <line x1="158" y1="40" x2="246" y2="40" stroke="#b45309" stroke-width="1.5"
          stroke-dasharray="4 3" marker-end="url(#ad)"/>
    <text x="166" y="32" font-size="9" fill="#b45309" font-weight="700">inferred 0.72</text>
    <path d="M340 62 L340 128" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>
    <text x="348" y="100" font-size="9" fill="#64748b">writes 0.85</text>
    <line x1="210" y1="154" x2="246" y2="154" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>
    <text x="212" y="146" font-size="9" fill="#64748b">stale 0.85</text>
    <line x1="430" y1="154" x2="476" y2="154" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>
    <text x="432" y="146" font-size="9" fill="#64748b">feeds 0.95</text>
    <line x1="660" y1="154" x2="696" y2="154" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>
    <rect x="480" y="110" width="104" height="16" rx="8" fill="#eef2ff"/>
    <text x="487" y="122" font-size="8.5" fill="#3730a3" font-weight="700">now · held here</text>
  </svg>
  <div class="cap">The break is upstream — the service is serving what it was given.</div>
  <div class="legend"><span><i></i>observed</span><span><i class="dash"></i>inferred</span>
    <span class="n">{esc(conn)}</span></div>
</div>'''


def _conn_line(ref):
    try:
        import graph
        rows = graph.store().neighbours(graph.incident_node_id(ref))
        obs = sum(1 for r in rows if r["edge"].get("basis") == "observed")
        return f'{len(rows)} connections · {obs} observed · {len(rows) - obs} inferred'
    except Exception:
        return "no connections recorded"


def _meaning(F, action):
    score = F["score"]
    if score is None:
        sentence = ("Observed links only on this thread — no inference has been recorded, so no "
                    "confidence is claimed.")
    else:
        sentence = (f'Upstream data is stale. Confidence {int(round(score * 100))}%, inferred — '
                    f'nobody has confirmed it yet.')
    ask = ""
    if F["asked"]:
        ask = (F["asked"].get("action") or "").split(" · expected in")[0]
    btn = (f'<a class="btn primary" href="?inc={esc(F["id"])}&action={esc(action)}" target="_top">'
           f'Chase {esc(F["holder"])}</a>' if action else "")
    return f'''<div class="card means">
  <h2>What this means</h2>
  <div class="big">{esc(sentence)}</div>
  <div class="next"><div class="l">Do this next</div>
    <div class="a">{esc(ask or "No action required")}</div>{btn}</div>
</div>'''


def _who(F):
    rows = []
    for name, role, extra in _people(F):
        initials = "".join(w[0] for w in str(name).split()[:2]).upper() or "•"
        rows.append(f'<div class="who"><span class="av">{esc(initials)}</span>'
                    f'<span><b>{esc(name)}</b><i>{esc(role)}</i></span>'
                    f'<em>{esc(extra)}</em></div>')
    return f'<div class="card who-card"><h2>Who is on it</h2>{"".join(rows)}</div>'


def _people(F):
    out = [(F["owns"], "owner", "")]
    if F["asked"]:
        out.append((F["asked"]["to_"], "asked",
                    f'asked {story.fmt_minutes(collab.age_minutes(F["asked"]))}'))
    return out[:3]


# ---------------------------------------------------------------- tabs
def _panes(F, dom):
    ref = F["id"]
    events = story._rows("SELECT kind, detail, ts FROM timeline WHERE ref_id=? ORDER BY ts DESC LIMIT 6",
                         (ref,))
    tl = "".join(
        f'<div class="ev"><span class="ts">{esc(str(e["ts"])[11:16])}</span>'
        f'<span class="tag {_tone(e["kind"])}">{esc(str(e["kind"]).upper())}</span>'
        f'<span>{esc(e["detail"])}</span></div>' for e in reversed(events))

    asks = [d for d in collab.delegations(ref)]
    req = "".join(
        f'<div class="req"><b>{esc(d["to_"])}</b> · {esc((d["action"] or "").split(" · expected in")[0])}'
        f'<span class="st {("od" if collab.is_overdue(d) and d["status"] != "done" else "sent")}">'
        f'{esc("OVERDUE" if collab.is_overdue(d) and d["status"] != "done" else d["status"])}</span>'
        f'<div class="muted">{esc(d.get("channel") or "App")} · recorded, simulated</div></div>'
        for d in sorted(asks, key=lambda d: d.get("ts") or "", reverse=True)[:4]) or \
        '<div class="muted">No request on this thread.</div>'

    ev = "".join(f'<div class="ev"><span>{esc(e)}</span></div>' for e in F["evidence"][:4]) or \
         '<div class="muted">No evidence recorded.</div>'
    sig = (f'{int(round(F["score"] * 100))}% inferred' if F["score"] is not None else "observed only")

    conn = _conn_line(ref)
    acts = story._rows("SELECT ts, detail FROM timeline WHERE ref_id=? ORDER BY ts DESC LIMIT 4", (ref,))
    audit = "".join(f'<div class="ev"><span class="ts">{esc(str(a["ts"])[11:16])}</span>'
                    f'<span>{esc(a["detail"])}</span></div>' for a in acts)

    rec = learn.get(ref) if hasattr(learn, "get") else None
    learn_body = (f'<div class="ev"><span><b>Saved</b> {esc(rec.get("saved_at", ""))} — '
                  f'{esc(rec.get("root_cause") or "")}</span></div>' if rec else
                  '<div class="ev"><span><b>Draft, not saved</b> — the record is written when the '
                  'incident closes and is verified.</span></div>')
    sig_name = ""
    try:
        sig_name = learn.signature(inc, "DataOps" if dom == "DataOps" else "IT Ops")
    except Exception:
        pass
    if sig_name:
        learn_body += (f'<div class="ev"><span class="muted">Signature <b>{esc(sig_name)}</b></span></div>')

    gate = F["gate"]
    actions = _act_links(F)

    return {
        "Timeline": tl,
        "Requests": req,
        "Evidence & RCA": ev,
        "Connections & audit": f'<div class="ev"><span>{esc(conn)}</span></div>{audit}',
        "Act & verify": actions,
        "Learn": learn_body,
    }


def _tone(kind):
    return {"alert": "warn", "impact": "warn", "repair": "bad"}.get(str(kind).lower(), "")


def _act_links(F):
    ref = F["id"]
    gate = F["gate"]
    rows = [
        ("Confirm cause", f'?inc={ref}&action=confirm', False,
         "recorded as a human confirmation"),
        ("Apply remediation", "", True, "inert in this POC — no change is executed"),
        ("Run verification", "", True, "inert in this POC — checks are recorded, not run"),
    ]
    if gate.get("eligible") and not gate.get("closed"):
        rows.append(("Close incident", f'?inc={ref}&action=close', False, "gap-gated"))
    else:
        rows.append(("Close incident", "", True, "blocked — " + ((gate.get("reasons") or ["requirement open"])[0][:60])))
    out = []
    for label, href, inert, why in rows:
        if inert:
            out.append(f'<div class="act inert"><span>{esc(label)}</span><i>{esc(why)}</i></div>')
        else:
            out.append(f'<a class="act" href="{href}" target="_top"><span>{esc(label)}</span>'
                       f'<i>{esc(why)}</i></a>')
    return "".join(out)


def _tabs(F, dom, initial):
    state = {
        "Timeline": f'{len(story._rows("SELECT id FROM timeline WHERE ref_id=?", (F["id"],)))} events',
        "Requests": ("1 OVERDUE" if any(collab.is_overdue(d) and d["status"] != "done"
                                        for d in collab.delegations(F["id"]))
                     else "none overdue"),
        "Evidence & RCA": f'{len(F["evidence"])} items',
        "Connections & audit": _conn_line(F["id"]).split(" · ")[0],
        "Act & verify": ("BLOCKED" if not F["gate"].get("closed") and not F["gate"].get("eligible")
                         else ("closed" if F["gate"].get("closed") else "ready")),
        "Learn": "saved" if (hasattr(learn, "get") and learn.get(F["id"])) else "draft",
    }
    bar = "".join(
        f'<button class="tab{" on" if name == initial else ""}" data-t="{i}">'
        f'{esc(name)}<b>{esc(state[name])}</b></button>'
        for i, name in enumerate(["Timeline", "Requests", "Evidence & RCA",
                                  "Connections & audit", "Act & verify", "Learn"]))
    panes = _panes(F, dom)
    body = "".join(
        f'<div class="pane{" on" if name == initial else ""}" id="p{i}">{panes[name]}'
        f'<button class="more" data-full="{esc(name)}">Show all</button>'
        f'<div class="full-src" hidden>{panes[name]}</div></div>'
        for i, name in enumerate(["Timeline", "Requests", "Evidence & RCA",
                                  "Connections & audit", "Act & verify", "Learn"]))
    return bar, body


# ---------------------------------------------------------------- document
CSS = """
:root{--accent:#4f46e5;--ink:#0f172a;--muted:#64748b;--line:#e5e7eb;--soft:#f8fafc;
 --red:#b91c1c;--amber:#b45309;--green:#166534;--teal:#0d9488}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:#fff;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 color:var(--ink);font-size:12.5px}
.wrap{display:grid;grid-template-rows:auto auto 1fr auto;gap:10px;height:756px;overflow:hidden;
 padding:6px 14px 4px;min-width:0}
.hdr,.tiles{min-width:0}
.hdr{min-height:46px}
.hdr .bc{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:800;display:flex;gap:10px;align-items:center}
.hdr .bc .back{color:var(--accent);text-decoration:none;text-transform:none;letter-spacing:0;font-size:10.5px}
.hdr .row{display:flex;align-items:center;gap:10px;white-space:nowrap;overflow:hidden}
.hdr .t{font-size:18px;font-weight:800;letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis}
.hdr .r{margin-left:auto;display:flex;align-items:center;gap:8px}
.pill{font-size:10px;font-weight:750;border:1px solid var(--line);border-radius:999px;padding:1px 8px;background:var(--soft)}
.hdr .q{font-size:11px;color:var(--muted)}
.hdr .clock{font-size:12.5px;font-weight:800}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.tile{border:1px solid var(--line);border-radius:10px;padding:5px 10px;height:74px;overflow:hidden;background:#fff}
.tile .k{font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:800}
.tile .v{font-size:18px;font-weight:800;line-height:1.15;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .q{font-size:10px;color:var(--muted);margin-top:1px}
.hero{display:grid;grid-template-columns:1.6fr 1fr;gap:10px;min-height:0;overflow:hidden}
.card{border:1px solid var(--line);border-radius:12px;background:#fff;padding:8px 11px;min-width:0;display:flex;flex-direction:column}
.card h2{margin:0 0 2px;font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.graph{flex:1;width:100%;min-height:0}
.cap{font-size:10.5px;color:#334155;border-top:1px solid var(--line);padding-top:4px;margin-top:2px}
.legend{display:flex;gap:12px;font-size:9.5px;color:var(--muted);margin-top:3px}
.legend i{display:inline-block;width:16px;height:0;border-top:2px solid #475569;vertical-align:3px;margin-right:4px}
.legend i.dash{border-top:2px dashed var(--amber)}
.legend .n{margin-left:auto}
.right{display:flex;flex-direction:column;gap:8px;min-height:0}
.means .big{font-size:12px;font-weight:650;line-height:1.4}
.means .next{margin-top:auto;border-top:1px solid var(--line);padding-top:6px}
.means .next .l{font-size:9px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:800}
.means .next .a{font-size:11.5px;font-weight:650;margin:1px 0 6px}
.btn{display:block;text-align:center;text-decoration:none;border-radius:8px;padding:6px 10px;font-size:11.5px;font-weight:750;border:1px solid var(--line);color:var(--ink);background:#fff}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.who-card .who{display:flex;align-items:center;gap:8px;margin-top:4px}
.who .av{width:20px;height:20px;border-radius:50%;background:#e5e7eb;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;color:#334155}
.who b{display:block;font-size:11px}
.who i{display:block;font-style:normal;font-size:9.5px;color:var(--muted)}
.who em{margin-left:auto;font-style:normal;font-size:9.5px;color:var(--muted)}
.tabbar{display:flex;align-items:stretch;gap:2px;border-bottom:1px solid var(--line)}
.tab{flex:1;background:none;border:none;border-bottom:2px solid transparent;text-align:left;cursor:pointer;padding:4px 2px;font-size:10.5px;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tab b{display:block;font-size:9.5px;color:var(--muted);font-weight:650}
.tab.on{border-bottom-color:var(--accent);color:var(--accent);font-weight:800}
.tab.on b{color:var(--accent)}
.band4{display:flex;flex-direction:column;min-height:0;overflow:hidden}
.panes{flex:1 1 auto;min-height:0;overflow:hidden}
.pane{display:none;height:100%;overflow:hidden;padding:6px 2px 0}
.pane.on{display:block}
.ev{display:flex;gap:8px;font-size:11px;padding:2px 0;align-items:baseline;flex-wrap:wrap}
.ev .ts{color:var(--muted);font-variant-numeric:tabular-nums;min-width:38px}
.tag{display:inline-block;font-size:8.5px;font-weight:800;border-radius:999px;padding:0 6px;color:#fff;background:#2563eb;margin-right:5px;flex:0 0 auto}
.tag.warn{background:var(--amber)}.tag.bad{background:var(--red)}
.req{border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:3px 8px;margin-bottom:4px;font-size:11px}
.st{font-size:8.5px;font-weight:800;text-transform:uppercase;border-radius:999px;padding:0 6px;margin-left:6px}
.st.od{color:var(--red);border:1px solid #fca5a5;background:#fef2f2}
.st.sent{color:#475569;border:1px dashed #94a3b8;background:var(--soft)}
.muted{color:var(--muted);font-size:10px}
.act{display:flex;justify-content:space-between;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:4px 9px;margin-bottom:4px;font-size:11px;font-weight:650}
.act i{font-style:normal;color:var(--muted);font-weight:500;font-size:9.5px}
.act.inert{opacity:.55;cursor:not-allowed}
.more{margin-top:2px;border:1px solid var(--line);background:#fff;border-radius:6px;padding:1px 8px;font-size:9.5px;color:var(--muted);cursor:pointer}
.foot{display:flex;justify-content:space-between;font-size:9.5px;color:var(--muted)}
.ov{grid-row:1 / -1;grid-column:1;background:rgba(15,23,42,.45);display:none;align-items:center;justify-content:center;z-index:50}
.ov.on{display:flex}
.ov .sheet{background:#fff;border-radius:14px;width:min(980px,92vw);height:min(660px,88vh);display:flex;flex-direction:column;padding:14px 18px}
.ov h3{margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.ov .body{flex:1;overflow:auto;font-size:12px}
.ov .close{position:static;align-self:flex-end;border:1px solid var(--line);background:#fff;border-radius:8px;padding:4px 10px;cursor:pointer;font-size:11px}
"""

JS = """
(function(){
  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var panes=[].slice.call(document.querySelectorAll('.pane'));
  function show(i){
    tabs.forEach(function(t,j){t.classList.toggle('on', j===i);});
    panes.forEach(function(p,j){p.classList.toggle('on', j===i);});
    try{var u=new URL(window.parent.location.href);u.searchParams.set('tab',tabs[i].innerText.split('\\n')[0]);window.parent.history.replaceState({},'',u);}catch(e){}
  }
  tabs.forEach(function(t,i){t.addEventListener('click',function(){show(i);});});
  var ov=document.getElementById('ov'), body=document.getElementById('ovbody'), title=document.getElementById('ovtitle');
  document.querySelectorAll('.more').forEach(function(b){
    b.addEventListener('click',function(){
      var name=b.getAttribute('data-full');
      var pane=b.parentElement.querySelector('.full-src');
      title.textContent=name; body.innerHTML=pane.innerHTML;
      ov.classList.add('on');
    });
  });
  document.getElementById('ovclose').addEventListener('click',function(){ov.classList.remove('on');});
  ov.addEventListener('click',function(e){if(e.target===ov)ov.classList.remove('on');});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')ov.classList.remove('on');});
})();
"""


def build(inc, dom, queue="", initial_tab="Timeline", action=None):
    """Return the whole incident screen as one HTML document."""
    F = facts(inc)
    bar, panes = _tabs(F, dom, initial_tab)
    act_href = None
    nxt = F["next"]
    if not F["gate"].get("closed") and F["asked"]:
        act_href = "chase"
    body = f'''<div class="wrap">
  <div class="r1">{_header(F, queue)}</div>
  <div class="r2">{_tiles(F)}</div>
  <div class="r3"><section class="hero">{_graph(F)}<div class="right">{_meaning(F, act_href)}{_who(F)}</div></section></div>
  <div class="r4 band4"><div class="tabbar">{bar}</div><div class="panes">{panes}</div></div>
  <div class="foot" style="grid-row:4"><span>Sample data · simulated actions · build v109</span>
    <span>{esc(F["id"])} · {esc(F["stage"])}</span></div>
  <div class="ov" id="ov"><div class="sheet">
    <button class="close" id="ovclose">Close</button>
    <h3 id="ovtitle"></h3><div class="body" id="ovbody"></div>
  </div></div>
</div>'''
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<style>{CSS}</style></head><body>{body}<script>{JS}</script></body></html>'''
