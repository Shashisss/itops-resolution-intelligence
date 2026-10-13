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


RESOLUTION_FLOW = ["Detection", "Triage", "Diagnosis", "Approval", "Repair", "Verification"]


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
