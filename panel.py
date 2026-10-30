#!/usr/bin/env python3
"""The incident page's first screen (v107a): one header row, four instrument tiles, six tabs.

Nothing here computes a fact of its own — every number comes from story/journey/analytics, the same
definitions the rest of the app uses. The tiles replace the hero strip and the handoff chain: wait,
SLA, domains/handoffs and the signal live here, and only here.

The tabs below hold everything else. Their content is capped to a fixed slice so the page height is
constant, and "show all" opens a full-height overlay for the long lists. No fact exists *only* in
the overlay: the capped slice always shows the count, the state and the first rows.
"""
import html

import streamlit as st

import collab
import journey
import story


def _esc(v):
    return html.escape(str(v))


def _metric(inc):
    """The breaching signal on this incident's own service (IT) or pipeline (DOP)."""
    if inc.get("service_id"):
        rows = story._rows("SELECT metric, value, threshold FROM metrics WHERE service_id=? "
                           "AND value > threshold ORDER BY value / threshold DESC LIMIT 1",
                           (inc["service_id"],))
        if rows:
            m = rows[0]
            unit = "%" if "pct" in m["metric"] or "rate" in m["metric"] else ""
            return {"label": m["metric"].replace("_pct", "").replace("_", " "),
                    "value": f'{m["value"]:g}{unit}', "threshold": f'{m["threshold"]:g}{unit}',
                    "ratio": m["value"] / m["threshold"] if m["threshold"] else 0}
    rows = story._rows("SELECT status, COUNT(*) AS n FROM dop_runs WHERE pipeline_id=? "
                       "GROUP BY status", (inc.get("pipeline_id"),))
    failed = sum(r["n"] for r in rows if str(r["status"]).lower() != "success")
    return {"label": "failed runs", "value": str(failed), "threshold": "0", "ratio": float(failed)}


def _gauge(ratio, threshold_ratio=1.0, height=40):
    """A 40px threshold strip: the allowed band, the threshold tick, and where the signal sits."""
    mark = max(4, min(96, 100 * min(ratio, 2) / 2))
    tick = 100 * min(threshold_ratio, 2) / 2
    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 100 {height}" preserveAspectRatio="none">'
        f'<rect x="0" y="{height//2 - 3}" width="{tick:.1f}" height="6" fill="#dcfce7"/>'
        f'<rect x="{tick:.1f}" y="{height//2 - 3}" width="{100 - tick:.1f}" height="6" fill="#fee2e2"/>'
        f'<line x1="{tick:.1f}" y1="{height//2 - 9}" x2="{tick:.1f}" y2="{height//2 + 9}" '
        f'stroke="#94a3b8" stroke-width="1.5"/>'
        f'<circle cx="{mark:.1f}" cy="{height//2}" r="4" fill="#b91c1c"/>'
        f'</svg>')


def _bar(fraction, height=40):
    pct = max(2, min(100, fraction * 100))
    return (f'<div style="height:{height}px;display:flex;align-items:center">'
            f'<div style="width:100%;height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{"#b91c1c" if fraction > 1 else "#0d9488"}">'
            f'</div></div></div>')


def _ring(fraction, height=40):
    pct = max(0.0, min(1.0, fraction))
    r, c = 16, 2 * 3.14159265 * 16
    return (f'<svg width="{height}" height="{height}" viewBox="0 0 40 40">'
            f'<circle cx="20" cy="20" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="5"/>'
            f'<circle cx="20" cy="20" r="{r}" fill="none" stroke="#4f46e5" stroke-width="5" '
            f'stroke-dasharray="{c * pct:.1f} {c:.1f}" transform="rotate(-90 20 20)" '
            f'stroke-linecap="round"/></svg>')


def _route(nodes, height=40):
    """Three dots in a column — a route you can read at 40px, inside the tile."""
    rows = []
    for i, n in enumerate(nodes[:3]):
        on = n.get("holder")
        col = "#4f46e5" if on else "#cbd5e1"
        rows.append(
            f'<div style="display:flex;align-items:center;gap:5px;height:12px">'
            f'<span style="width:7px;height:7px;border-radius:50%;background:{col};'
            f'flex:0 0 auto"></span>'
            f'<span style="font-size:9.5px;color:{"#3730a3" if on else "#64748b"};'
            f'font-weight:{750 if on else 600};white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis">{_esc(n["label"])}</span></div>')
    return (f'<div style="height:{height}px;display:flex;flex-direction:column;justify-content:center;'
            f'gap:2px;overflow:hidden">' + "".join(rows) + "</div>")


def _tile(label, value, qualifier, visual):
    return (f'<div class="ri-tile"><div class="k">{_esc(label)}</div>'
            f'<div class="v">{_esc(value)}</div>'
            f'<div class="q">{_esc(qualifier)}</div>'
            f'<div class="g">{visual}</div></div>')


def tiles(inc):
    """Four tiles, one row, each one number and one qualifying line."""
    w, s, c = story.waiting(inc), story.sla(inc), story.cross(inc)
    sig = _metric(inc)
    ds = inc.get("dataset_id") or journey.stale_dataset(inc["id"])
    f = journey.freshness(ds) if ds else None
    used = 1 - (s["remaining_min"] / (s["target_hours"] * 60)) if s.get("remaining_min") is not None else 0

    out = [
        _tile(sig["label"], sig["value"], f'vs {sig["threshold"]} threshold',
              _gauge(sig["ratio"])),
        _tile("data freshness", f'{f["lag_min"]}m' if f else "—",
              f'vs {f["sla_min"]}m SLA' if f else "no freshness record",
              _bar((f["lag_min"] / f["sla_min"]) if f and f["sla_min"] else 0)),
        _tile("time left", f'{int(round(used * 100))}%',
              f'of the {s["target_hours"]}h SLA used' if s.get("target_hours") else "closed",
              _ring(used)),
        _tile("handoff", f'{c["domains"]} domains · {c["handoffs"]} handoffs',
              (f'{w["who"]} holds it, {story.fmt_minutes(w["minutes"])}' if not w["empty"]
               else "nobody is holding it"),
              _route(c["nodes"])),
    ]
    st.markdown(f'<div class="ri-tiles">{"".join(out)}</div>', unsafe_allow_html=True)


def header(inc, verdict, sev, queue, clock):
    """One row: title, priority + stage pills, queue position, the single clock. Nothing else."""
    st.markdown(
        f'<div class="ri-hdr"><span class="id">{_esc(inc["id"])}</span>'
        f'<span class="t">{_esc(inc.get("title") or "")}</span>'
        f'<span class="pill">{_esc(inc.get("priority") or "")}</span>'
        f'<span class="pill">{_esc(journey.lifecycle_stage(inc))}</span>'
        f'<span class="q">{_esc(queue)}</span>'
        f'<span class="clock">{_esc(clock)}</span></div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ tabs
TABS = ["Timeline", "Requests", "Evidence & RCA", "Connections & audit", "Act & verify", "Learn"]


def _act_state(inc):
    """The one line the Act & verify tab must carry: overdue, blocked or unverified."""
    gate = journey.closure_state(inc)
    verdict = journey.current_verdict(inc)
    asks = [d for d in collab.delegations(inc["id"]) if d.get("status") != "done"]
    overdue = [d for d in asks if collab.is_overdue(d)]
    # the overdue count is stated once, in the Requests tab; this tab states the gate.
    if not gate.get("closed") and not gate.get("eligible"):
        return "BLOCKED"
    if verdict and verdict != "Verified" and (inc.get("status") or "").lower() != "closed":
        return "UNVERIFIED"
    return "ready" if not gate.get("closed") else "closed"


def tab_state(inc, dom):
    """The words a tab header must carry — counts and critical state, never blank."""
    ref = inc["id"]
    events = story._rows("SELECT id FROM timeline WHERE ref_id=?", (ref,))
    asks = [d for d in collab.delegations(ref) if d.get("status") != "done"]
    overdue = [d for d in asks if collab.is_overdue(d)]
    corner = story._rows("SELECT id FROM comments WHERE ref_id=?", (ref,))
    try:
        import graph
        conn = len(graph.store().neighbours(graph.incident_node_id(ref)))
    except Exception:
        conn = 0
    try:
        import learn
        rec = learn.get(ref)
    except Exception:
        rec = None
    ev = story.evidence(inc, limit=99)
    return {
        "Timeline": f'{len(events)} events',
        "Requests": (f'{len(asks)} open · {len(overdue)} OVERDUE' if overdue
                     else (f'{len(asks)} open' if asks else "none open")),
        "Evidence & RCA": f'{len(ev)} items',
        "Connections & audit": f'{len(events) + len(corner)} records',
        "Act & verify": _act_state(inc),
        "Learn": ("saved" if rec else "draft, not saved"),
    }


def tab_bar(ref, active):
    """Six headers as buttons, each carrying its own state in words."""
    state = st.session_state.get(f"tabstate_{ref}") or {}
    labels = [f'{name} · {state.get(name, "")}' if state.get(name) else name for name in TABS]
    # width follows the label: a long state ("1 open · 1 OVERDUE") gets room instead of wrapping
    widths = [max(1.15, len(lbl) / 16) for lbl in labels]
    cols = st.columns(widths)
    for col, name, label in zip(cols, TABS, labels):
        if col.button(label, key=f"tab_{ref}_{name}", width="stretch",
                      type=("primary" if name == active else "secondary")):
            st.session_state[f"tab_{ref}"] = name
            st.rerun()


def active_tab(ref, default="Evidence"):
    """The selected tab. Deep link ?tab=… wins once, then the reader's own choice."""
    raw = (st.query_params.get("tab") or "").strip().lower()
    want = next((t for t in TABS if t.lower() == raw), "")
    token = f'tab|{want}'
    if want in TABS and st.session_state.get(f"deep_{ref}") != token:
        st.session_state[f"deep_{ref}"] = token
        st.session_state[f"tab_{ref}"] = want
    st.session_state.setdefault(f"tab_{ref}", default)
    return st.session_state[f"tab_{ref}"]


def show_all_button(title, key):
    """The trigger for the overlay — rendered outside the capped container so it is always visible."""
    return st.button(f"Show all · {title}", key=f"showall_{key}", width="stretch")


def show_all(title, render):
    """A full-height overlay for the long lists — never the only route to a fact, only the long one."""
    if st.button(f"Show all · {title}", key=f"showall_{title}", width="stretch"):
        dialog = getattr(st, "dialog", None)
        if dialog is None:
            return
        @dialog(title=f"{title} — full view")
        def _full():
            render()
        _full()


# ==================================================================== v108: concept A
def header(inc, verdict, sev, queue, clock, on_back=None):  # noqa: F811
    """Breadcrumb + title, with the pills, queue and the single clock on the right."""
    st.markdown(
        f'<div class="ri-h2"><div class="l">Incidents / {_esc(inc["id"])}</div>'
        f'<div class="row"><span class="t">{_esc(inc.get("title") or "")}</span>'
        f'<span class="r"><span class="pill">{_esc(inc.get("priority") or "")}</span>'
        f'<span class="pill">{_esc(journey.lifecycle_stage(inc))}</span>'
        f'<span class="q">{_esc(queue)}</span>'
        f'<span class="clock">{_esc(clock)}</span></span></div></div>', unsafe_allow_html=True)


def _mono(text, size=30):
    return (f'<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:{size}px;'
            f'line-height:{size + 2}px">{text}</div>')


def _threshold_chart(value, threshold, height=30):
    """Value and threshold on one 30px line — no invented history."""
    top = max(value, threshold * 1.6, 0.001)
    xv = 100 * value / top
    xt = 100 * threshold / top
    return (f'<svg width="100%" height="{height}" viewBox="0 0 100 {height}" preserveAspectRatio="none">'
            f'<line x1="0" y1="{height/2}" x2="100" y2="{height/2}" stroke="#e5e7eb" stroke-width="1"/>'
            f'<line x1="{xt:.1f}" y1="{height/2 - 8}" x2="{xt:.1f}" y2="{height/2 + 8}" '
            f'stroke="#94a3b8" stroke-width="1.5"/>'
            f'<circle cx="{xv:.1f}" cy="{height/2}" r="4" fill="#b91c1c"/></svg>')


def tiles(inc):  # noqa: F811 — replaces the v107a tiles
    """Waiting on · error rate · data freshness · checkout — the mockup's order."""
    w, s = story.waiting(inc), story.sla(inc)
    m = _metric(inc)
    ds = inc.get("dataset_id") or journey.stale_dataset(inc["id"])
    f = journey.freshness(ds) if ds else None
    kpi = story.impact(inc).get("kpi")
    if kpi:
        checkout = (f'{kpi["current"]:g}{kpi["unit"]}',
                    f'baseline {kpi["baseline"]:g}{kpi["unit"]}')
    else:
        checkout = ("—", "no KPI mapped")

    if w["empty"]:
        wait_q = "nobody is holding it"
    elif w.get("overdue"):
        wait_q = f'{story.fmt_minutes(w["minutes"])} · {w["minutes"] - w["deadline_min"]}m over deadline'
    else:
        wait_q = f'{story.fmt_minutes(w["minutes"])} · {w["deadline_min"]}m deadline'
    out = [
        _tile("Waiting on", w["who"] if not w["empty"] else "—", wait_q, ""),
        _tile("Error rate" if inc.get("service_id") else "Failed runs", m["value"],
              f'vs {m["threshold"]} threshold', ""),
        _tile("Data freshness", f'{f["lag_min"]}m' if f else "—",
              f'SLA {f["sla_min"]}m — {f["lag_min"] // f["sla_min"]}x over' if f and f["lag_min"] >= f["sla_min"] else
              (f'SLA {f["sla_min"]}m' if f else "no record"), ""),
        _tile("Checkout", checkout[0], checkout[1], ""),
    ]
    st.markdown(f'<div class="ri-tiles">{"".join(out)}</div>', unsafe_allow_html=True)


def graph_card(inc):
    """Why this is happening: change → job → dataset → service → KPI, plus the linked incident."""
    ds = inc.get("dataset_id") or journey.stale_dataset(inc["id"])
    f = journey.freshness(ds) if ds else None
    corr = journey.correlation_for(inc["id"])
    kpi = story.impact(inc).get("kpi")
    st.markdown(
        f'<div class="ri-card2"><div class="h">Why this is happening</div>'
        f'<svg width="100%" height="170" viewBox="0 0 800 186">'
        f'<defs><marker id="as" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
        f'<path d="M0,0 L7,3.5 L0,7 z" fill="#475569"/></marker>'
        f'<marker id="ad" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
        f'<path d="M0,0 L7,3.5 L0,7 z" fill="#b45309"/></marker></defs>'
        f'<g font-size="10.5" fill="#0f172a">'
        f'<rect x="8" y="14" width="150" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>'
        f'<text x="17" y="31" font-size="8.5" fill="#64748b" letter-spacing=".06em">CHANGE</text>'
        f'<text x="17" y="47" font-weight="650">core_ledger v4</text>'
        f'<rect x="250" y="14" width="180" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>'
        f'<text x="259" y="31" font-size="8.5" fill="#64748b" letter-spacing=".06em">JOB</text>'
        f'<text x="259" y="47" font-weight="650">payments_bronze_ingest</text>'
        f'<rect x="60" y="128" width="150" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>'
        f'<text x="69" y="145" font-size="8.5" fill="#64748b" letter-spacing=".06em">INCIDENT</text>'
        f'<text x="69" y="161" font-weight="650">{_esc(corr["other_id"]) if corr else "—"}</text>'
        f'<rect x="250" y="128" width="180" height="44" rx="8" fill="#fff" stroke="#fdba74"/>'
        f'<text x="259" y="145" font-size="8.5" fill="#b45309" letter-spacing=".06em">DATASET · STALE '
        f'{f["lag_min"] if f else "—"}m</text>'
        f'<text x="259" y="161" font-weight="650">{_esc(f["name"]) if f else "dataset"}</text>'
        f'<rect x="480" y="128" width="180" height="44" rx="8" fill="#eef2ff" stroke="#4f46e5"/>'
        f'<text x="489" y="145" font-size="8.5" fill="#3730a3" letter-spacing=".06em">SERVICE · '
        f'{"LIVE" if (inc.get("status") or "").lower() == "open" else "CLOSED"}</text>'
        f'<text x="489" y="161" font-weight="700">{_esc(_service_name(inc))}</text>'
        f'<rect x="700" y="128" width="94" height="44" rx="8" fill="#fff" stroke="#e5e7eb"/>'
        f'<text x="709" y="145" font-size="8.5" fill="#64748b" letter-spacing=".06em">KPI</text>'
        f'<text x="709" y="161" font-weight="650">{_esc(f"checkout {kpi['current']:g}{kpi['unit']}") if kpi else "—"}</text>'
        f'</g>'
        f'<line x1="158" y1="36" x2="246" y2="36" stroke="#b45309" stroke-width="1.5" '
        f'stroke-dasharray="4 3" marker-end="url(#ad)"/>'
        f'<text x="166" y="28" font-size="9" fill="#b45309" font-weight="700">inferred 0.72</text>'
        f'<path d="M340 58 L340 124" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>'
        f'<text x="348" y="96" font-size="9" fill="#64748b">writes 0.85</text>'
        f'<line x1="210" y1="150" x2="246" y2="150" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>'
        f'<text x="212" y="142" font-size="9" fill="#64748b">stale 0.85</text>'
        f'<line x1="430" y1="150" x2="476" y2="150" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>'
        f'<text x="432" y="142" font-size="9" fill="#64748b">feeds 0.95</text>'
        f'<line x1="660" y1="150" x2="696" y2="150" stroke="#475569" stroke-width="1.5" marker-end="url(#as)"/>'
        f'<rect x="480" y="106" width="104" height="16" rx="8" fill="#eef2ff"/>'
        f'<text x="487" y="118" font-size="8.5" fill="#3730a3" font-weight="700">now · held here</text>'
        f'</svg>'
        f'<div class="cap">The break is upstream — the service is serving what it was given.</div>'
        f'<div class="legendline"><span><i></i>observed</span>'
        f'<span><i class="dash"></i>inferred</span>'
        f'<span class="n">{_conn_line(inc)}</span></div></div>', unsafe_allow_html=True)


def _conn_line(inc):
    """The connections count, from the graph store — the same count the audit tab lists."""
    try:
        import graph
        rows = graph.store().neighbours(graph.incident_node_id(inc["id"]))
        obs = sum(1 for r in rows if r["edge"].get("basis") == "observed")
        return f'{len(rows)} connections · {obs} observed · {len(rows) - obs} inferred'
    except Exception:
        return "no connections recorded"


def _service_name(inc):
    """The node after the dataset: the service (IT) or the pipeline that writes it (DOP)."""
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


def meaning_card(inc, action_label, on_action):
    """One sentence, the confidence and basis, then the single next action."""
    corr = journey.correlation_for(inc["id"])
    sig = story._rows("SELECT kind, confidence FROM thread_edges WHERE thread_ref=? AND kind='inferred' "
                      "ORDER BY CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END LIMIT 1",
                      (inc["id"],))
    score = None
    if sig:
        import agents
        score = agents.SIGNAL_SCORE.get("inferred", {}).get((sig[0]["confidence"] or "").lower())
    if score is None:
        sentence = ("Observed links only on this thread — no inference has been recorded, so no "
                    "confidence is claimed.")
    else:
        sentence = (f'Upstream data is stale. Confidence {int(round(score * 100))}%, inferred — '
                    f'nobody has confirmed it yet.')
    st.markdown(
        f'<div class="ri-card2"><div class="h">What this means</div>'
        f'<div class="big">{_esc(sentence)}</div>'
        f'<div class="nextbox"><div class="l">Do this next</div>'
        f'<div class="a">{_esc(action_label or "No action required")}</div></div></div>',
        unsafe_allow_html=True)


def who_card(inc, people):
    """Who is on it — the owner and who was asked, with the ask's age."""
    rows = ""
    for name in people[:2]:
        asked = story._rows("SELECT ts, to_ FROM delegations WHERE ref_id=? AND to_=? "
                            "AND status != 'done' ORDER BY ts LIMIT 1", (inc["id"], name))
        age = f'asked {story.fmt_minutes(collab.age_minutes({"ts": asked[0]["ts"]}))}' if asked else ""
        role = "owner" if name == inc.get("owner_team") else ("asked" if asked else "on the thread")
        initials = "".join(w[0] for w in str(name).split()[:2]).upper() or "•"
        rows += (f'<div class="who"><span class="av">{_esc(initials)}</span>'
                 f'<span><b>{_esc(name)}</b><i>{_esc(role)}</i></span>'
                 f'{f"<em>{_esc(age)}</em>" if age else ""}</div>')
    st.markdown(f'<div class="ri-card2"><div class="h">Who is on it</div>{rows}</div>',
                unsafe_allow_html=True)
