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
    if overdue:
        return f'{len(overdue)} OVERDUE'
    if not gate.get("closed") and not gate.get("eligible"):
        reason = (gate.get("reasons") or ["blocked"])[0]
        return "BLOCKED: " + (reason[:34] + "…" if len(reason) > 34 else reason)
    if verdict and verdict != "Verified" and (inc.get("status") or "").lower() != "closed":
        return f'UNVERIFIED: {verdict}'
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
        "Connections & audit": (f'{conn} links · {len(events) + len(corner)} records' if conn
                                else f'{len(events) + len(corner)} records'),
        "Act & verify": _act_state(inc),
        "Learn": ("saved" if rec else "draft, not saved"),
    }


def tab_bar(ref, active):
    """Six headers as buttons, each carrying its own state in words."""
    state = st.session_state.get(f"tabstate_{ref}") or {}
    cols = st.columns(len(TABS))
    for col, name in zip(cols, TABS):
        label = f'{name} · {state.get(name, "")}' if state.get(name) else name
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


def full_view(name, dom, ref, inc, you_role):
    """The overlay: the same body, uncapped, in a dialog. Never the only route to a fact."""
    import app as _app            # late import: the tab bodies live in app.py
    dialog = getattr(st, "dialog", None)
    if dialog is None:
        return

    @dialog(title=f"{name} — {ref}", width="large")
    def _full():
        _app._tab_body(name, dom, ref, inc, you_role)

    _full()
