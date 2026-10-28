#!/usr/bin/env python3
"""Connections panel — the incident's neighbours, read through the graph store.

A list, not a picture: on a projector a tidy list of named connections with their provenance beats
a hairball, and every row can carry the two things a claim needs — where it came from, and how sure
we are. Observed and inferred are visually distinct, because an observed metric and the inference
that it caused the incident are not the same kind of fact.
"""
import html

import streamlit as st

import graph
import journey

# Human reading of each edge type: (group title, one line under it)
EDGE_LABEL = {
    "caused_by": ("Caused by", "what this incident is attributed to"),
    "evidenced_by": ("Evidenced by", "signals recorded against it"),
    "affects": ("Affects", "business service and KPI impact"),
    "observed_in": ("Observed in", "where it was seen"),
    "depends_on": ("Depends on", "dependencies it inherits"),
    "resolved_by": ("Resolved by", "runbook, ticket or team that owns the fix"),
    "learned_from": ("Learned from", "prior knowledge it reuses"),
}

_CSS = """<style>
.ri-conn {display:flex;gap:10px;align-items:baseline;padding:6px 10px;margin:0 0 4px;
  border-left:3px solid #e2e8f0;background:#fbfdff;border-radius:0 6px 6px 0;flex-wrap:wrap}
.ri-conn.obs {border-left-color:#0f766e}
.ri-conn.inf {border-left-color:#b45309;border-left-style:dashed}
.ri-conn-type {font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:#64748b;
  min-width:52px;font-weight:700}
.ri-conn-name {font-weight:600;color:#0f172a}
.ri-conn-basis {font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px}
.ri-conn-basis.obs {background:#ccfbf1;color:#0f766e;border:1px solid #5eead4}
.ri-conn-basis.inf {background:#fef3c7;color:#92400e;border:1px dashed #f59e0b}
.ri-conn-src {flex-basis:100%;font-size:11.5px;color:#64748b;margin-top:2px}
.ri-conn-src b {color:#475569;font-weight:600}
.ri-conn-head {font-size:12px;color:#64748b;margin:10px 0 5px;font-weight:700;
  letter-spacing:.03em;text-transform:uppercase}
</style>"""


def _label(node):
    props = node.get("properties") or {}
    if node.get("type") == "Signal":
        if props.get("metric"):
            return f'{props["metric"]} {props.get("value"):g} vs {props.get("threshold"):g}'
        if props.get("dataset"):
            # live staleness, not the number frozen when the graph was projected
            ds = node["id"].split(":", 2)[-1]
            f = journey.freshness(ds)
            lag = f["lag_min"] if f else props.get("lag_min")
            sla = f["sla_min"] if f else props.get("sla_min")
            return f'{props["dataset"]} stale · {lag}m > {sla}m SLA'
        if props.get("run"):
            return f'run {props["run"]} failed'
    for key in ("name", "label", "title", "metric", "description", "detail", "mode"):
        if props.get(key):
            return str(props[key])
    return node.get("business_key") or node["id"]


def _short(text, limit=150):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def connections_panel(inc_id, store=None, dataset=None, key="connections"):
    """Render the selected node's neighbours, grouped by edge type. Returns the rows, or []."""
    g = store or graph.store()
    node_id = graph.incident_node_id(inc_id)
    node = g.node(node_id)
    if not node:
        return []
    rows = g.neighbours(node_id)
    if not rows:
        st.caption("No connections recorded for this incident yet.")
        return []

    ds = dataset or journey.stale_dataset(inc_id)
    observed = sum(1 for r in rows if r["edge"].get("basis") == "observed")
    inferred = len(rows) - observed
    st.markdown(_CSS, unsafe_allow_html=True)
    st.caption(f"{len(rows)} connections · {observed} observed · {inferred} inferred — "
               f"each row carries the source it came from and the confidence in the link.")

    order = [t for t in graph.EDGE_TYPES if any(r["edge"]["type"] == t for r in rows)]
    for etype in order:
        group = [r for r in rows if r["edge"]["type"] == etype]
        title, note = EDGE_LABEL.get(etype, (etype.replace("_", " ").capitalize(), ""))
        st.markdown(f'<div class="ri-conn-head">{html.escape(title)} · {len(group)}'
                    f'<span style="font-weight:400;text-transform:none;letter-spacing:0"> — '
                    f'{html.escape(note)}</span></div>', unsafe_allow_html=True)
        for r in group:
            edge, other = r["edge"], r["node"]
            basis = edge.get("basis") or "inferred"
            conf = edge.get("confidence")
            conf_txt = f"{float(conf):.2f}" if conf is not None else "—"
            arrow = "→" if r["direction"] == "out" else "←"
            source = journey._stale_text(edge.get("source") or "—", ds)
            st.markdown(
                f'<div class="ri-conn {"obs" if basis == "observed" else "inf"}">'
                f'<span class="ri-conn-type">{html.escape(other["type"])}</span>'
                f'<span class="ri-conn-name">{arrow} '
                f'{html.escape(_short(journey._stale_text(_label(other), ds), 72))}</span>'
                f'<span class="ri-conn-basis {"obs" if basis == "observed" else "inf"}">'
                f'{basis} · {conf_txt}</span>'
                f'<span class="ri-conn-src"><b>source</b> {html.escape(_short(source))}</span>'
                f'</div>', unsafe_allow_html=True)
    return rows


def summary(inc_id, store=None):
    """One line for the identity bar: how much graph is behind this incident."""
    g = store or graph.store()
    rows = g.neighbours(graph.incident_node_id(inc_id))
    if not rows:
        return None
    observed = sum(1 for r in rows if r["edge"].get("basis") == "observed")
    return f"{len(rows)} connections · {observed} observed · {len(rows) - observed} inferred"
