#!/usr/bin/env python3
"""Visual layer — animated steppers, arrow flows, node graphs and status badges (HTML/CSS + Graphviz)."""
import pandas as pd
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
.block-container{padding-top:1.0rem;padding-bottom:1.25rem}
div[data-testid="stVerticalBlock"]{gap:0.5rem}
.ri-topbrand{font-weight:800;font-size:19px;color:#0f172a;letter-spacing:-.01em;margin:0 0 4px}
.ri-topbrand span{color:#64748b;font-weight:600;font-size:12.5px}
/* All-incidents board: each incident is ONE clickable card (a full-width keyed button). */
div[class*="st-key-boardcard-"] button{width:100%!important;text-align:left!important;
  justify-content:flex-start!important;height:auto!important;white-space:normal!important;
  background:#fff!important;color:#0f172a!important;border:1px solid #e5e7eb!important;
  border-left:6px solid #94a3b8!important;border-radius:12px!important;padding:11px 14px!important;
  font-weight:600!important;font-size:13px!important;line-height:1.4!important;
  box-shadow:0 1px 2px rgba(0,0,0,.04)!important;margin:2px 0!important}
div[class*="st-key-boardcard-"] button p{font-weight:600!important;font-size:13px!important;
  line-height:1.4!important;margin:0!important;text-align:left!important;color:#0f172a!important}
div[class*="st-key-boardcard-"] button:hover{background:#f8fafc!important}
div[class*="st-key-boardcard-P1-"] button{border-left-color:#dc2626!important}
div[class*="st-key-boardcard-P2-"] button{border-left-color:#d97706!important}
div[class*="st-key-boardcard-P3-"] button{border-left-color:#0891b2!important}
div[class*="st-key-boardcard-P4-"] button{border-left-color:#64748b!important}
/* Clickable KPI cards (filters) */
div[class*="st-key-kpi_"] button{height:auto!important;width:100%!important;text-align:left!important;
  justify-content:flex-start!important;white-space:normal!important;background:#fff!important;color:#0f172a!important;
  border:1px solid #e5e7eb!important;border-left:5px solid #4f46e5!important;border-radius:12px!important;
  padding:11px 14px!important;box-shadow:0 1px 2px rgba(0,0,0,.04)!important}
div[class*="st-key-kpi_"] button p{font-weight:700!important;font-size:15px!important;text-align:left!important;
  color:#0f172a!important;margin:0!important}
div[class*="st-key-kpi_"] button:hover{background:#f8fafc!important}
/* Ambient live strip — global, always-visible (one compact line) */
.ri-ambient{display:flex;gap:9px;flex-wrap:wrap;align-items:center;background:#f8fafc;
  border:1px solid #e5e7eb;border-radius:10px;padding:6px 11px;margin:0 0 10px}
.ri-ambient .ri-amb-l{font-weight:800;font-size:11.5px;color:#0f172a;white-space:nowrap}
.ri-amb{border-left:3px solid #94a3b8;padding:1px 9px;font-size:11.5px;color:#334155;white-space:nowrap}
/* ---- readability: typography scale + tighter cards (build v64) ---- */
.ri-tag{font-size:11.5px!important}
.ri-kpi .l{font-size:12px!important}
.ri-kpi .s{font-size:12.5px!important}
.ri-kpi .v{font-size:20px!important}
.ri-ev-chip{font-size:13.5px!important}
.ri-lc-stage{font-size:13.5px!important}
.ri-tl-kind{font-size:12px!important}
.ri-amb{font-size:12.5px!important}
.ri-hero .id{font-size:24px!important}
.ri-hero .meta{font-size:13.5px!important}
div[class*="st-key-boardcard-"] button p{font-size:13.5px!important}
div[class*="st-key-kpi_"] button p{font-size:16px!important}
div[class*="st-key-boardcard-"] button{padding:8px 12px!important;border-radius:10px!important;
  border-left-width:4px!important}
div[class*="st-key-boardcard-"] button p{line-height:1.35!important}
.ri-card{padding:12px 14px!important}
.ri-kpi{padding:10px 12px!important}
.ri-hero{padding:16px 20px!important}
/* ---- design tokens + responsive guards (build v51) ---- */
:root{--ri-accent:#4f46e5;--ri-ink:#0f172a;--ri-muted:#64748b;--ri-line:#e5e7eb;--ri-soft:#f8fafc;--ri-r:12px}
.ri-hero .id,.ri-card,.ri-kpi .v,.ri-kpi .s,.ri-ev-chip,.ri-qcard,.ri-lc-stage{overflow-wrap:anywhere;word-break:break-word}
.ri-hero>div{flex-wrap:wrap}
.ri-kpi .v{line-height:1.25}
.ri-kpi .s{line-height:1.3}
/* lifecycle: compact progress strip (status via symbol AND border colour AND tooltip text) */
.ri-lc{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:2px 0 6px}
.ri-lc-stage{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;
  font-size:12.5px;font-weight:700;border:1px solid var(--ri-line);background:#fff;color:var(--ri-ink)}
.ri-lc-stage.done{border-color:#16a34a;color:#166534;background:#f0fdf4}
.ri-lc-stage.current{border-color:var(--ri-accent);color:#3730a3;background:#eef2ff}
.ri-lc-stage.blocked{border-color:#d97706;color:#92400e;background:#fffbeb}
.ri-lc-stage.failed{border-color:#dc2626;color:#991b1b;background:#fef2f2}
.ri-lc-stage.todo{color:#94a3b8;background:#fff}
.ri-lc-arrow{color:#cbd5e1;font-weight:700}
/* tabs wrap instead of clipping on narrow screens */
.stTabs [data-baseweb="tab-list"]{flex-wrap:wrap!important;gap:2px!important}
.stTabs [data-baseweb="tab"]{white-space:normal!important}
/* columns must be allowed to shrink (prevents clipping/overflow) */
[data-testid="stHorizontalBlock"]{flex-wrap:wrap}
[data-testid="column"]{min-width:0}
@media (max-width:640px){.ri-hero{padding:14px 16px}.ri-hero .id{font-size:18px}.ri-flowbox{gap:6px}}
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
            f'<div style="font-size:14px;font-weight:700;color:#0f172a">{icon} '
            f'{h.get("label") or h.get("type","").title()}'
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


_DOM = {"DataOps": "#0d9488", "IT Ops": "#4f46e5"}


def causal(steps):
    """Cross-domain causal chain. steps: list of (label, domain)."""
    html = ['<div class="ri-flowbox">']
    for i, (lab, dom) in enumerate(steps):
        c = _DOM.get(dom, "#64748b")
        html.append(f'<div style="text-align:center">'
                    f'<div style="background:{c}1a;border:1px solid {c};border-radius:10px;padding:8px 12px;'
                    f'color:#0f172a;font-weight:600;font-size:13px">{lab}</div>'
                    f'<div style="font-size:10px;color:{c};margin-top:2px;text-transform:uppercase;'
                    f'letter-spacing:.05em">{dom}</div></div>')
        if i < len(steps) - 1:
            html.append('<span class="ri-arrow2">➜</span>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def impact_summary(metric, baseline, current, unit, onset_label, onset):
    delta = (current or 0) - (baseline or 0)
    st.markdown(
        f'<div class="ri-card"><div style="font-size:10.5px;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:.04em">{metric}</div>'
        f'<div style="display:flex;gap:30px;align-items:baseline;margin-top:8px;flex-wrap:wrap">'
        f'<div><div style="font-size:11px;color:#64748b">baseline</div>'
        f'<div style="font-size:18px;font-weight:700;color:#0f172a">{baseline}{unit}</div></div>'
        f'<div><div style="font-size:11px;color:#64748b">current</div>'
        f'<div style="font-size:26px;font-weight:800;color:#dc2626">{current}{unit}</div></div>'
        f'<div><div style="font-size:11px;color:#64748b">delta</div>'
        f'<div style="font-size:18px;font-weight:700;color:#d97706">{delta:+.1f}{unit}</div></div>'
        f'<div><div style="font-size:11px;color:#64748b">{onset_label}</div>'
        f'<div style="font-size:18px;font-weight:700;color:#0f172a">{onset}</div></div>'
        f'</div></div>', unsafe_allow_html=True)


def thread_spine(items):
    """items: list of (title, status, detail, ola). status in done/current/blocked/failed/todo;
    ola = stage internal target."""
    cols = {"done": "#16a34a", "current": "#4f46e5", "blocked": "#d97706", "failed": "#dc2626",
            "todo": "#cbd5e1"}
    html = ['<div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 12px">']
    for i, (title, status, detail, ola) in enumerate(items):
        c = cols.get(status, "#cbd5e1")
        ola_tag = (f'<div style="margin-top:7px"><span class="ri-tag" style="background:#0891b2">'
                   f'OLA · {ola}</span></div>') if ola else ""
        html.append(f'<div class="ri-card" style="flex:1;min-width:140px;border-top:4px solid {c}">'
                    f'<div style="font-size:10.5px;color:#64748b;text-transform:uppercase;letter-spacing:.04em">'
                    f'{i + 1} · {status}</div>'
                    f'<div style="font-weight:700;color:#0f172a;margin:2px 0 3px">{title}</div>'
                    f'<div style="font-size:12px;color:#475569">{detail}</div>{ola_tag}</div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


_LC_SYM = {"done": "✔", "current": "●", "blocked": "⏸", "failed": "✖", "todo": "○"}


def lifecycle_strip(items):
    """Compact shared lifecycle strip: one chip per stage (status shown by symbol + border colour
    + tooltip), not a row of equally-large cards."""
    html = ['<div class="ri-lc">']
    for i, (title, status, detail, ola) in enumerate(items):
        cls = status if status in _LC_SYM else "todo"
        tip = detail + (f' · OLA {ola}' if ola else "")
        html.append(f'<span class="ri-lc-stage {cls}" title="{tip}">'
                    f'{_LC_SYM[cls]} {title}</span>')
        if i < len(items) - 1:
            html.append('<span class="ri-lc-arrow">→</span>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def audit_record(rows, ref):
    st.markdown(f"**Auditable verification record** · ref `{ref}`")
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True)
    st.download_button("⬇ Download ledger (CSV)", data=df.to_csv(index=False).encode("utf-8"),
                       file_name=f"evidence_{ref}.csv", mime="text/csv", key="dl_" + ref)
    st.caption("Each row records **source · action reference · observed value · threshold · timestamp · verifying "
               "actor · result** — independent of the operator. A record is not a closure unless every check passes.")


def thread_edges(edges):
    """edges: list of dicts {src, rel, dst, kind (observed|inferred), source, ts}.
    Supports multiple contributing causes and distinguishes observed from inferred links."""
    for e in edges:
        kcol = {"observed": "#16a34a", "inferred": "#d97706"}.get(e["kind"], "#64748b")
        st.markdown(
            f'<div class="ri-card" style="padding:9px 12px;margin:6px 0">'
            f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
            f'<span class="ri-tag" style="background:#0f172a">{e["src"]}</span>'
            f'<span style="color:#64748b;font-size:12px">{e["rel"]} ➜</span>'
            f'<span class="ri-tag" style="background:#4f46e5">{e["dst"]}</span>'
            f'<span class="ri-tag" style="background:{kcol}">{e["kind"]}</span></div>'
            f'<div style="font-size:11.5px;color:#64748b;margin-top:4px">source: {e.get("source","")}'
            f'{(" · " + e["ts"]) if e.get("ts") else ""}</div></div>', unsafe_allow_html=True)


def value_strip(rows, note="Simulated demo values — establish a real baseline and measure in a pilot.",
                title="Impact — resolution acceleration (illustrative)"):
    """rows: list of (metric, baseline, observed)."""
    st.markdown(f"#### {title}")
    for m, b, o in rows:
        st.markdown(f'<div class="ri-ev-chip" style="border-left-color:#4f46e5">'
                    f'<b>{m}</b> · baseline <b>{b}</b> ➜ observed <b style="color:#16a34a">{o}</b></div>',
                    unsafe_allow_html=True)
    st.caption(note)


def collab_strip(owner, next_actor, stats):
    """Prominent collaboration banner — collaboration is the resolution accelerator."""
    parts = " · ".join(stats.get("participants", [])[:5]) or "—"
    co = f'{stats["coord_min"]} min' if stats.get("coord_min") is not None else "—"

    def cell(k, v):
        return (f'<div style="min-width:110px"><div style="font-size:10.5px;color:#64748b;'
                f'text-transform:uppercase;letter-spacing:.04em">{k}</div>'
                f'<div style="font-size:16px;font-weight:800;color:#0f172a">{v}</div></div>')

    st.markdown(
        f'<div class="ri-card" style="border-left:6px solid #4f46e5;background:#f7f8ff">'
        f'<div style="display:flex;gap:22px;flex-wrap:wrap">'
        + cell("Owner", owner) + cell("Next actor", next_actor)
        + cell("Participants", len(stats.get("participants", [])))
        + cell("Handoffs", f'{stats.get("handoffs", 0)} ({stats.get("handoffs_done", 0)} done)')
        + cell("Coordinated in", co) + cell("Thread updates", stats.get("updates", 0))
        + '</div>'
        f'<div style="font-size:11.5px;color:#64748b;margin-top:7px">engaged: {parts}</div></div>',
        unsafe_allow_html=True)


def next_step(action, owner, gate, why=None, target=None, blast=None, risk=None):
    """Prominent 'recommended next step' banner — action, owner, gate, and why/target/blast/risk."""
    extra = " · ".join(x for x in (
        f"why: {why}" if why else "",
        f"target: {target}" if target else "",
        f"blast: {blast}" if blast else "",
        f"risk: {risk}" if risk else "",
    ) if x)
    st.markdown(
        f'<div class="ri-card" style="border-left:6px solid #4f46e5;background:#eef2ff">'
        f'<div style="font-size:10.5px;color:#64748b;text-transform:uppercase;letter-spacing:.04em">'
        f'Recommended next step</div>'
        f'<div style="font-weight:700;color:#0f172a;margin:3px 0;font-size:14px">{action}</div>'
        f'<div style="font-size:12px;color:#334155">owner: <b>{owner}</b> · gate: <b>{gate}</b></div>'
        + (f'<div style="font-size:11.5px;color:#64748b;margin-top:3px">{extra}</div>' if extra else "")
        + '</div>', unsafe_allow_html=True)


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
        hhmm = ts.split("T")[-1][:5] if "T" in ts else ts
        st.markdown(
            f'<div class="ri-feed" style="border-left-color:{col}">'
            f'<div style="display:flex;justify-content:space-between;gap:8px;align-items:center">'
            f'<span title="{ts}" style="font-size:12px;color:#64748b">{hhmm}</span>'
            f'<span><span class="ri-tag" style="background:{dc}">{dom}</span> '
            f'<span class="ri-tag" style="background:{col}">{e.get("severity","")}</span></span></div>'
            f'<div style="margin-top:4px;font-size:13px"><b>{e.get("source","")}</b> — '
            f'{e.get("message","")}</div></div>', unsafe_allow_html=True)


def ambient_strip(events):
    """Compact global live strip (chips only; the caller provides the collapsible label)."""
    if not events:
        st.caption("No events yet.")
        return
    parts = []
    for e in events[:6]:
        col = SEV_COLOR.get(e.get("severity"), "#94a3b8")
        dom = "DataOps" if e.get("domain") == "dataops" else "IT Ops"
        ts = str(e.get("ts", ""))
        hhmm = ts.split("T")[-1][:5] if "T" in ts else ts
        msg = str(e.get("message", ""))
        if len(msg) > 44:
            msg = msg[:42] + "…"
        parts.append(f'<span class="ri-amb" style="border-left-color:{col}">'
                     f'<b style="color:{col}">{hhmm}</b> {dom} · {msg}</span>')
    st.markdown('<div class="ri-ambient">' + "".join(parts) + '</div>', unsafe_allow_html=True)


SEV_LABEL = {"P1": ("🔴", "Critical"), "P2": ("🟠", "Major"), "P3": ("🔵", "Minor"),
             "P4": ("⚪", "Low")}


def board_card(inc, domain, verdict, on_click, args, stage=None, sla=None, open_=False, linked=False):
    """Compact incident row (Linear-style): line 1 = ID + title; line 2 = severity · status ·
    domain · owner · time. The whole row is clickable (keyed button styled as a card); the
    per-priority left border and 🔗 marker carry severity and cross-domain at a glance."""
    pri = inc.get("priority", "P3")
    status = (inc.get("status") or "open").title()
    owner = inc.get("owner_team") or "—"
    mark = "▾" if open_ else "▸"
    link = "🔗 " if linked else ""
    icon, sev = SEV_LABEL.get(pri, ("🔵", "Minor"))
    line1 = f'{mark}{link}**{inc["id"]}**  {inc["title"]}'
    line2 = f'{icon} {sev} · {status} · {domain} · {owner}' + (f' · ⏱ {sla}' if sla else '')
    st.button(f'{line1}  \n{line2}', key=f'boardcard-{pri}-{inc["id"]}', width="stretch",
              on_click=on_click, args=args)


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
