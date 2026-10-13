#!/usr/bin/env python3
"""Visual layer — animated steppers, arrow flows, node graphs and status badges (HTML/CSS + Graphviz)."""
import streamlit as st

CSS = """
<style>
.ri-flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:4px 0 12px}
.ri-step{padding:7px 13px;border-radius:10px;font-weight:600;font-size:13px;color:#fff;background:#cbd5e1}
.ri-step.done{background:#16a34a}
.ri-step.current{background:#4f46e5;animation:ripulse 1.6s infinite}
.ri-step.todo{background:#e5e7eb;color:#6b7280}
.ri-arrow{font-size:16px;color:#94a3b8;animation:rislide 1.2s infinite}
.ri-arrow.hot{color:#4f46e5}
@keyframes rislide{0%{transform:translateX(-2px);opacity:.45}50%{transform:translateX(3px);opacity:1}100%{transform:translateX(-2px);opacity:.45}}
@keyframes ripulse{0%{box-shadow:0 0 0 0 rgba(79,70,229,.5)}70%{box-shadow:0 0 0 10px rgba(79,70,229,0)}100%{box-shadow:0 0 0 0 rgba(79,70,229,0)}}
.ri-badge{display:inline-flex;align-items:center;gap:8px;padding:7px 16px;border-radius:999px;font-weight:700;color:#fff;font-size:14px}
.ri-dot{width:10px;height:10px;border-radius:50%;background:#fff;animation:ripulse 1.4s infinite}
.ri-card{border:1px solid #e5e7eb;border-radius:14px;padding:14px 16px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.ri-flowbox{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:6px 0 14px}
.ri-nbox{padding:9px 14px;border-radius:12px;font-weight:600;font-size:13px;color:#fff;background:#4f46e5}
.ri-nbox.alt{background:#0d9488}.ri-nbox.warn{background:#d97706}.ri-nbox.bad{background:#dc2626}.ri-nbox.good{background:#16a34a}
.ri-arrow2{font-size:20px;color:#4f46e5}
.ri-tl{position:relative;padding-left:26px;border-left:2px solid #e5e7eb;margin:8px 0 12px}
.ri-tl-item{position:relative;margin:0 0 15px}
.ri-tl-dot{position:absolute;left:-33px;top:3px;width:13px;height:13px;border-radius:50%;border:2px solid #fff}
.ri-ev-grp{font-size:12px;font-weight:700;margin:10px 0 5px;letter-spacing:.02em}
.ri-ev-chip{border-left:4px solid #94a3b8;background:#f8fafc;padding:6px 11px;border-radius:8px;margin:4px 0;font-size:12.5px;color:#334155}
.ri-tl-kind{color:#fff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;text-transform:capitalize}
@keyframes rislidein{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.ri-feed{border-left:5px solid #94a3b8;background:#f8fafc;border-radius:10px;padding:8px 12px;margin:6px 0;animation:rislidein .5s ease}
.ri-qcard{border:1px solid #e5e7eb;border-left:6px solid #94a3b8;border-radius:12px;padding:10px 14px;margin:8px 0;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.ri-tag{color:#fff;font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px}
.ri-hero{border-radius:16px;padding:18px 22px;color:#fff;background:linear-gradient(100deg,#0b1220 0%,#2a1a63 60%,#4f46e5 130%);margin:0 0 12px}
.ri-hero .id{font-size:22px;font-weight:800;letter-spacing:-.01em;margin:8px 0 2px}
.ri-hero .meta{color:#c7d2fe;font-size:12.5px}
.ri-kpi{border:1px solid #e5e7eb;border-left:5px solid #2563eb;border-radius:12px;padding:11px 13px;background:#fff;height:100%}
.ri-kpi .l{font-size:10.5px;color:#64748b;text-transform:uppercase;letter-spacing:.04em}
.ri-kpi .v{font-size:18px;font-weight:800;color:#0f172a;margin-top:2px}
.ri-kpi .s{font-size:11.5px;color:#64748b;margin-top:2px}
.ri-rail{border:1px solid #e5e7eb;border-radius:14px;padding:12px 14px;background:#fff;margin-bottom:12px}
.ri-rail h4{margin:0 0 8px;font-size:13px;color:#0f172a}
.ri-brand{background:linear-gradient(100deg,#0b1220,#3b1d6e);border-radius:12px;padding:12px 14px;color:#fff;margin-bottom:10px}
.ri-brand .t{font-weight:800;font-size:15px}
.ri-brand .s{color:#c7d2fe;font-size:11px}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def stepper(stages, current):
    idx = stages.index(current) if current in stages else 0
    html = ['<div class="ri-flow">']
    for i, s in enumerate(stages):
        cls = "done" if i < idx else ("current" if i == idx else "todo")
        html.append(f'<span class="ri-step {cls}">{s}</span>')
        if i < len(stages) - 1:
            hot = " hot" if i == idx - 1 or i == idx else ""
            html.append(f'<span class="ri-arrow{hot}">➜</span>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def verdict_badge(state):
    colors = {"Investigating": "#2563eb", "Mitigated": "#d97706", "Verified": "#16a34a",
              "Recovery failed": "#dc2626"}
    c = colors.get(state, "#64748b")
    st.markdown(f'<div class="ri-badge" style="background:{c}"><span class="ri-dot"></span>{state}</div>',
                unsafe_allow_html=True)


RESOLUTION_FLOW = ["Detect", "Diagnose", "Decide", "Act", "Verify"]


def resolution_flow(current=None):
    html = ['<div class="ri-flowbox">']
    for i, s in enumerate(RESOLUTION_FLOW):
        cls = "ri-nbox"
        if s == current:
            cls += " warn"
        elif current and RESOLUTION_FLOW.index(current) > i:
            cls += " good"
        html.append(f'<span class="{cls}">{s}</span>')
        if i < len(RESOLUTION_FLOW) - 1:
            html.append('<span class="ri-arrow2">➜</span>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


CONF_PCT = {"high": 85, "medium": 55, "low": 30}
CONF_COLOR = {"high": "#16a34a", "medium": "#d97706", "low": "#94a3b8"}
TYPE_ICON = {"pipeline": "🛠️", "data quality": "🧪", "freshness": "⏱️", "upstream data": "🔗",
             "change": "🔧", "metric": "📈"}


def hypothesis_cards(hyps):
    """Render RCA hypotheses as visual cards with confidence bars, badges and evidence."""
    for i, h in enumerate(hyps):
        conf = h.get("confidence", "low")
        pct = CONF_PCT.get(conf, 30)
        col = CONF_COLOR.get(conf, "#94a3b8")
        confirmed = h.get("status") == "confirmed"
        badge = "✅ CONFIRMED" if confirmed else "🔶 SUSPECTED"
        badgecol = "#16a34a" if confirmed else "#d97706"
        bg = "#f0fdf4" if confirmed else "#ffffff"
        icon = TYPE_ICON.get(h.get("type", ""), "🔎")
        top = ('<span style="background:#4f46e5;color:#fff;font-size:10px;font-weight:700;'
               'padding:2px 8px;border-radius:999px;margin-left:8px">MOST LIKELY</span>') if i == 0 else ""
        st.markdown(
            f'<div style="border:1px solid #e5e7eb;border-left:7px solid {col};border-radius:12px;'
            f'padding:12px 15px;margin:9px 0;background:{bg};box-shadow:0 1px 2px rgba(0,0,0,.05)">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a">{icon} {h.get("type","").title()}'
            f'{top}<div style="font-weight:500;color:#334155;margin-top:3px">{h.get("text","")}</div></div>'
            f'<span style="white-space:nowrap;background:{badgecol};color:#fff;font-weight:700;font-size:11px;'
            f'padding:3px 10px;border-radius:999px">{badge}</span></div>'
            f'<div style="margin:9px 0 3px"><div style="height:8px;background:#e5e7eb;border-radius:999px;'
            f'overflow:hidden"><div style="height:8px;width:{pct}%;background:{col};border-radius:999px">'
            f'</div></div><div style="font-size:12px;color:#64748b;margin-top:4px">confidence: '
            f'<b>{conf}</b> ({pct}%)</div></div>'
            f'<div style="font-size:12.5px;color:#475569">🔎 evidence: {h.get("evidence","")}</div>'
            f'</div>',
            unsafe_allow_html=True)


import re

TL_COLOR = {"change": "#7c3aed", "alert": "#dc2626", "incident": "#4f46e5", "ticket": "#0891b2",
            "impact": "#d97706", "repair": "#16a34a", "verify": "#16a34a", "detect": "#2563eb"}
TL_ICON = {"change": "🔧", "alert": "🚨", "incident": "📟", "ticket": "🎫", "impact": "📉",
           "repair": "🛠️", "verify": "✅", "detect": "🔎"}


def timeline(rows):
    html = ['<div class="ri-tl">']
    for r in rows:
        col = TL_COLOR.get(r["kind"], "#94a3b8")
        ic = TL_ICON.get(r["kind"], "•")
        ts = str(r.get("ts", ""))
        tshow = ts[11:16] if len(ts) >= 16 else ts
        html.append(
            f'<div class="ri-tl-item"><span class="ri-tl-dot" style="background:{col};'
            f'box-shadow:0 0 0 2px {col}"></span>'
            f'<div style="font-size:12px;color:#64748b">{tshow}</div>'
            f'<div style="margin-top:3px"><span class="ri-tl-kind" style="background:{col}">{ic} {r["kind"]}</span>'
            f' <span style="color:#334155;font-size:13px">{r["detail"]}</span></div></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


EVID_COLOR = {"INC": "#4f46e5", "JIRA": "#2563eb", "CHG": "#7c3aed", "METRIC": "#d97706",
              "KPI": "#0d9488", "GRAPH": "#475569", "SIMILAR": "#94a3b8", "UPSTREAM": "#dc2626"}


def evidence(items):
    groups = {}
    for it in items:
        m = re.match(r"\[(\w+)\]\s*(.*)", str(it))
        t, body = (m.group(1), m.group(2)) if m else ("OTHER", str(it))
        groups.setdefault(t, []).append(body)
    for t, rows in groups.items():
        col = EVID_COLOR.get(t, "#64748b")
        st.markdown(f'<div class="ri-ev-grp" style="color:{col}">{t} · {len(rows)}</div>', unsafe_allow_html=True)
        for b in rows:
            st.markdown(f'<div class="ri-ev-chip" style="border-left-color:{col}">{b}</div>', unsafe_allow_html=True)


SEV_COLOR = {"info": "#16a34a", "warning": "#d97706", "critical": "#dc2626"}
PRI_COLOR = {"P1": "#dc2626", "P2": "#d97706", "P3": "#0891b2", "P4": "#64748b"}
DOM_COLOR = {"itops": "#4f46e5", "IT Ops": "#4f46e5", "dataops": "#0d9488", "DataOps": "#0d9488"}


LEGEND = [
    ("Domain", [("IT Ops", "#4f46e5"), ("DataOps", "#0d9488")]),
    ("Severity", [("info", "#16a34a"), ("warning", "#d97706"), ("critical", "#dc2626")]),
    ("Priority", [("P1", "#dc2626"), ("P2", "#d97706"), ("P3", "#0891b2")]),
    ("Confidence", [("high", "#16a34a"), ("medium", "#d97706"), ("low", "#94a3b8")]),
    ("Status", [("assigned", "#d97706"), ("accepted", "#0891b2"), ("done", "#16a34a")]),
    ("Autonomy", [("coordination · auto", "#16a34a"), ("execution · approval", "#dc2626")]),
]


def legend():
    for group, items in LEGEND:
        chips = " ".join(f'<span class="ri-tag" style="background:{c}">{t}</span>' for t, c in items)
        st.markdown(f'<div style="margin:4px 0"><span style="color:#64748b;font-size:10.5px;'
                    f'text-transform:uppercase;letter-spacing:.04em">{group}</span><br>{chips}</div>',
                    unsafe_allow_html=True)


def card_rows(rows, border="#94a3b8"):
    """Render tabular rows as chips (keeps the visual language consistent)."""
    for r in rows:
        parts = " · ".join(f'<b>{k}</b>: {v}' for k, v in r.items())
        st.markdown(f'<div class="ri-ev-chip" style="border-left-color:{border}">{parts}</div>',
                    unsafe_allow_html=True)


def fact_cards(items):
    """Label/value cards that WRAP long values and expose the full text on hover (title tooltip)."""
    cols = st.columns(len(items))
    for col, (label, value, color) in zip(cols, items):
        col.markdown(
            f'<div class="ri-card" style="border-left:5px solid {color};padding:9px 12px" '
            f'title="{value}">'
            f'<div style="font-size:10.5px;color:#64748b;text-transform:uppercase;letter-spacing:.04em">'
            f'{label}</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a;white-space:normal;'
            f'word-break:break-word;margin-top:2px">{value}</div></div>',
            unsafe_allow_html=True)


def brand():
    st.sidebar.markdown('<div class="ri-brand"><div class="t">Resolution Intelligence</div>'
                        '<div class="s">IT Ops + DataOps · unified operational resolution</div></div>',
                        unsafe_allow_html=True)


def hero(priority, inc_id, title, meta, sla_text, verdict, chips):
    chip_html = " ".join(f'<span class="ri-tag" style="background:#1e293b;border:1px solid #334155">{c}</span>'
                         for c in chips)
    vcol = {"Verified": "#16a34a", "Mitigated": "#d97706", "Recovery failed": "#dc2626"}.get(verdict, "#2563eb")
    st.markdown(
        f'<div class="ri-hero"><div style="display:flex;justify-content:space-between;gap:16px">'
        f'<div><span class="ri-tag" style="background:#dc2626">{priority}</span> '
        f'<span class="ri-tag" style="background:{vcol}">{verdict}</span>'
        f'<div class="id">{inc_id} · {title}</div>'
        f'<div class="meta">{meta}</div></div>'
        f'<div style="text-align:right;white-space:nowrap">'
        f'<div class="meta">SLA remaining</div>'
        f'<div style="font-size:26px;font-weight:800;color:#fca5a5">{sla_text}</div>'
        f'<div style="margin-top:6px">{chip_html}</div></div></div></div>',
        unsafe_allow_html=True)


def kpi_row(items):
    """items: list of (label, value, sub, color)."""
    cols = st.columns(len(items))
    for col, (label, value, sub, color) in zip(cols, items):
        col.markdown(f'<div class="ri-kpi" style="border-left-color:{color}" title="{label}: {value}">'
                     f'<div class="l">{label}</div><div class="v">{value}</div>'
                     f'<div class="s">{sub}</div></div>', unsafe_allow_html=True)


def handshake(text):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:9px;background:#EEF2FF;border-left:4px solid '
        f'#4f46e5;padding:8px 12px;border-radius:8px;margin:2px 0 10px;font-size:13px">'
        f'<span style="font-size:16px">🤝</span><span><b>Handshake</b> — {text}</span></div>',
        unsafe_allow_html=True)


def status_bar(text):
    st.markdown(f'<div style="position:sticky;top:0;z-index:99;background:#0b1220;color:#fff;'
                f'padding:7px 14px;border-radius:10px;font-size:13px;font-weight:600;margin:2px 0 10px">'
                f'{text}</div>', unsafe_allow_html=True)


def rec_card(action, risk, mode, actors):
    riskcol = ("#dc2626" if str(risk).lower().startswith("high")
               else "#d97706" if str(risk).lower().startswith(("medium", "low"))
               else "#16a34a")
    modecol = {"Human approval": "#dc2626", "Policy controlled": "#d97706",
               "Auto": "#16a34a", "Autonomous": "#16a34a"}.get(mode, "#64748b")
    chips = " ".join(f'<span class="ri-tag" style="background:#4f46e5">{a}</span>' for a in actors)
    st.markdown(
        f'<div class="ri-card" style="border-left:6px solid #4f46e5">'
        f'<div style="font-weight:700;color:#0f172a;font-size:14px">🧭 Recommended action</div>'
        f'<div style="color:#334155;margin:6px 0 10px;font-size:13.5px">{action}</div>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">'
        f'<span class="ri-tag" style="background:{riskcol}">risk: {risk}</span>'
        f'<span class="ri-tag" style="background:{modecol}">gate: {mode}</span>'
        f'<span style="color:#64748b;font-size:12px">next actor ➜</span> {chips}</div></div>',
        unsafe_allow_html=True)


def feed(events):
    for e in events:
        col = SEV_COLOR.get(e.get("severity"), "#94a3b8")
        dc = DOM_COLOR.get(e.get("domain"), "#64748b")
        dom = "IT" if e.get("domain") == "itops" else "Data"
        ts = str(e.get("ts", ""))
        st.markdown(
            f'<div class="ri-feed" style="border-left-color:{col}">'
            f'<div style="display:flex;justify-content:space-between;gap:8px;align-items:center">'
            f'<span style="font-size:12px;color:#64748b">{ts[11:19] if len(ts)>=19 else ts}</span>'
            f'<span><span class="ri-tag" style="background:{dc}">{dom}</span> '
            f'<span class="ri-tag" style="background:{col}">{e.get("severity","")}</span></span></div>'
            f'<div style="margin-top:4px;font-size:13px"><b>{e.get("source","")}</b> — '
            f'{e.get("message","")}</div></div>', unsafe_allow_html=True)


def queue_cards(rows):
    for r in rows:
        pc = PRI_COLOR.get(r["priority"], "#64748b")
        dc = DOM_COLOR.get(r["domain"], "#64748b")
        st.markdown(
            f'<div class="ri-qcard" style="border-left-color:{pc}">'
            f'<div style="display:flex;justify-content:space-between;gap:8px;align-items:center">'
            f'<div style="font-weight:700;color:#0f172a;font-size:14px">{r["ref"]} '
            f'<span class="ri-tag" style="background:{dc}">{r["domain"]}</span></div>'
            f'<span class="ri-tag" style="background:{pc}">{r["priority"]}</span></div>'
            f'<div style="color:#334155;font-size:13px;margin-top:4px">{r["title"]}</div>'
            f'<div style="color:#64748b;font-size:12px;margin-top:3px">Owner: {r["owner"]}</div></div>',
            unsafe_allow_html=True)


def chain(seq, labels, stale=(), highlight=(), arrows=True):
    """Horizontal, animated arrow chain of nodes (source → … → consumer)."""
    html = ['<div class="ri-flowbox">']
    for i, n in enumerate(seq):
        cls = "ri-nbox"
        if n in stale:
            cls += " bad"
        elif n in highlight:
            cls += " good"
        html.append(f'<span class="{cls}">{labels.get(n, n)}</span>')
        if arrows and i < len(seq) - 1:
            html.append('<span class="ri-arrow2">➜</span>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
