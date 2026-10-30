#!/usr/bin/env python3
"""Visual layer — animated steppers, arrow flows, node graphs and status badges (HTML/CSS + Graphviz)."""
import html
import re

import altair as alt
import pandas as pd
import streamlit as st

CSS = """
<style>
.ri-flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0 0 4px}
.ri-step{padding:4px 11px;border-radius:9px;font-weight:600;font-size:12.5px;color:#fff;background:#cbd5e1}
.ri-step.done{background:#16a34a}
.ri-step.current{background:#4f46e5;animation:ripulse 1.6s infinite}
.ri-step.todo{background:#e5e7eb;color:#6b7280}
.ri-substep{display:block;font-size:10.5px;font-weight:600;letter-spacing:.04em;opacity:.9;margin-top:1px}
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
.ri-sidebrand{font-weight:800;font-size:17px;color:#0f172a;line-height:1.25;margin:0 0 10px}
.ri-sidebrand span{font-weight:600;font-size:11.5px;color:#475569}
.ri-kpi{min-width:0}
.ri-kpi .v{overflow-wrap:break-word!important;word-break:normal!important;hyphens:none!important}
.ri-kpi .s{overflow-wrap:break-word!important;word-break:normal!important;hyphens:none!important}
/* All-incidents board: each incident is ONE clickable card (a full-width keyed button). */
div[class*="st-key-boardcard-"] button,div[class*="st-key-attn-"] button{width:100%!important;text-align:left!important;
  justify-content:flex-start!important;height:auto!important;white-space:normal!important;
  background:#fff!important;color:#0f172a!important;border:1px solid #e5e7eb!important;
  border-left:6px solid #94a3b8!important;border-radius:12px!important;padding:11px 14px!important;
  font-weight:600!important;font-size:13px!important;line-height:1.4!important;
  box-shadow:0 1px 2px rgba(0,0,0,.04)!important;margin:2px 0!important}
div[class*="st-key-boardcard-"] button p,div[class*="st-key-attn-"] button p{font-weight:600!important;font-size:13px!important;
  line-height:1.4!important;margin:0!important;text-align:left!important;color:#0f172a!important;
  white-space:normal!important;overflow:visible!important;text-overflow:clip!important;
  width:100%!important;display:block!important}
div[class*="st-key-boardcard-"] button,div[class*="st-key-attn-"] button:hover{background:#f8fafc!important}
div[class*="st-key-boardcard-P1-"] button,div[class*="st-key-attn-P1-"] button{border-left-color:#dc2626!important}
div[class*="st-key-boardcard-P2-"] button,div[class*="st-key-attn-P2-"] button{border-left-color:#d97706!important}
div[class*="st-key-boardcard-P3-"] button,div[class*="st-key-attn-P3-"] button{border-left-color:#0891b2!important}
div[class*="st-key-boardcard-P4-"] button,div[class*="st-key-attn-P4-"] button{border-left-color:#64748b!important}
/* Clickable KPI cards (filters) */
div[class*="st-key-kpi_"] button{height:auto!important;width:100%!important;text-align:left!important;
  justify-content:flex-start!important;white-space:normal!important;background:#fff!important;color:#0f172a!important;
  border:1px solid #e5e7eb!important;border-left:5px solid #4f46e5!important;border-radius:12px!important;
  padding:11px 14px!important;box-shadow:0 1px 2px rgba(0,0,0,.04)!important}
div[class*="st-key-kpi_"] button p{font-weight:700!important;font-size:15px!important;text-align:left!important;
  color:#0f172a!important;margin:0!important}
div[class*="st-key-kpi_"] button:hover{background:#f8fafc!important}
/* lifecycle stage buttons: each stage in its own colour (no default blue primary) */
div[class*="st-key-lcb_"] button{background:#fff!important;border:1px solid #e5e7eb!important;
  border-left:4px solid #94a3b8!important;border-radius:10px!important}
div[class*="st-key-lcb_"] button p{font-weight:700!important;font-size:12.5px!important}
div[class*="st-key-lcb_"][class*="_Detect"] button{border-left-color:#2A66BE!important}
div[class*="st-key-lcb_"][class*="_Detect"] button p{color:#2A66BE!important}
div[class*="st-key-lcb_"][class*="_Correlate"] button{border-left-color:#7A4FBF!important}
div[class*="st-key-lcb_"][class*="_Correlate"] button p{color:#7A4FBF!important}
div[class*="st-key-lcb_"][class*="_Coordinate"] button{border-left-color:#D98B2B!important}
div[class*="st-key-lcb_"][class*="_Coordinate"] button p{color:#B45309!important}
div[class*="st-key-lcb_"][class*="_Act"] button{border-left-color:#C2410C!important}
div[class*="st-key-lcb_"][class*="_Act"] button p{color:#C2410C!important}
div[class*="st-key-lcb_"][class*="_Verify"] button{border-left-color:#2E8B62!important}
div[class*="st-key-lcb_"][class*="_Verify"] button p{color:#2E8B62!important}
div[class*="st-key-lcb_"][class*="_Close"] button{border-left-color:#475569!important}
div[class*="st-key-lcb_"][class*="_Close"] button p{color:#475569!important}
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
div[class*="st-key-boardcard-"] button p,div[class*="st-key-attn-"] button p{font-size:13.5px!important}
div[class*="st-key-kpi_"] button p{font-size:16px!important}
div[class*="st-key-boardcard-"] button,div[class*="st-key-attn-"] button{padding:8px 12px!important;border-radius:10px!important;
  border-left-width:4px!important}
div[class*="st-key-boardcard-"] button p,div[class*="st-key-attn-"] button p{line-height:1.35!important}
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
/* ---- fact grid: never break a word across lines, never clip a fact (v76) ---- */
.ri-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:8px;margin:4px 0 10px}
.ri-facts .ri-kpi{height:auto;min-width:0}
.ri-facts .ri-kpi .v{font-size:19px;line-height:1.2;white-space:normal;overflow-wrap:normal;
  word-break:keep-all;hyphens:none;font-variant-numeric:tabular-nums}
.ri-facts .ri-kpi .v.sm{font-size:15px;font-weight:750;letter-spacing:-.005em}
.ri-facts .ri-kpi .v.xs{font-size:13.5px;font-weight:700}
.ri-facts .ri-kpi .s{font-size:11.5px;line-height:1.35}
/* provenance + chart chrome */
.ri-prov{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
  letter-spacing:.03em;text-transform:uppercase;padding:2px 8px;border-radius:999px;margin:0 0 6px}
.ri-prov.live{background:#eef2ff;color:#4338ca;border:1px solid #c7d2fe}
.ri-prov.illus{background:#f8fafc;color:#64748b;border:1px dashed #cbd5e1}
.ri-prov .d{width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block}
.ri-chartnote{font-size:11.5px;color:#64748b;margin:-2px 0 10px}
/* section headings: no decorative emoji, tighter rhythm (v76) */
.ri-sect{font-size:13px;font-weight:800;color:#0f172a;letter-spacing:.01em;margin:6px 0 6px}
/* ---- v77: page header, breadcrumb, participants, sections ---- */
.ri-phead{padding:0 0 2px}
.ri-phead .t{font-size:28px;font-weight:800;letter-spacing:-.02em;color:#0f172a;line-height:1.15}
.ri-phead .s{font-size:13.5px;color:#64748b;margin-top:3px}
.ri-phead .s b{color:#334155}
.ri-phead .t.sid{font-size:21px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:-.01em}
.ri-participants{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:2px 0 10px}
.ri-person{display:inline-flex;align-items:center;gap:7px;background:#fff;border:1px solid #e5e7eb;
  border-radius:999px;padding:3px 10px 3px 3px;font-size:12px;color:#334155}
.ri-person b{font-weight:650}
.ri-avatar{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;
  border-radius:50%;background:#eef2ff;color:#4338ca;font-size:10px;font-weight:800;letter-spacing:.02em}
.ri-person:before{content:"";width:22px;height:22px;border-radius:50%;background:#eef2ff;display:none}
.ri-gate{display:flex;gap:8px;align-items:center;border-radius:10px;padding:9px 12px;font-size:12.5px;
  border:1px solid #fde68a;background:#fffbeb;color:#92400e;margin:2px 0 8px}
.ri-gate.ok{background:#f0fdf4;border-color:#bbf7d0;color:#166534}
.ri-gate b{font-weight:750}
.ri-sbctx{border:1px solid #e5e7eb;border-left:4px solid #4f46e5;border-radius:10px;
  padding:8px 10px;margin:6px 0 2px;background:#fff}
.ri-sbctx .l{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#64748b;font-weight:700}
.ri-sbctx .id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:800;font-size:15px;
  color:#0f172a;margin:1px 0 3px}
.ri-sbctx .chip{display:inline-block;font-size:11px;font-weight:750;padding:1px 8px;border-radius:999px}
.ri-sbctx .meta{font-size:11.5px;color:#64748b;margin-top:2px}
.ri-sbctx .meta b{color:#0f172a}
.ri-filterchip{display:inline-block;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe;
  font-size:11.5px;font-weight:650;padding:3px 9px;border-radius:999px;margin:0 6px 4px 0}
.ri-scope{display:inline-block;background:#4f46e5;color:#fff;font-size:11.5px;font-weight:700;
  padding:3px 10px;border-radius:999px;margin:0 6px 4px 0}
input:focus-visible,textarea:focus-visible,button:focus-visible,[role=button]:focus-visible{
  outline:2px solid #4f46e5!important;outline-offset:2px!important}
/* The identity bar must stay visible while the thread scrolls. Streamlit wraps each st.container in a
   layout div of equal height, which caps position:sticky — so that wrapper is taken out of flow.
   --ri-head is the height of Streamlit's own header (the Fork/source toolbar on a published app,
   60px; 0 locally), measured at runtime by viz.platform_offset(): without it the bar pins underneath
   that header and is invisible on Cloud. */
/* The identity bar stays on screen while the page scrolls. Sticky goes on the bar's *layout
   wrapper*, not on the bar: Streamlit gives that wrapper exactly the bar's height, so sticky on the
   bar never has room to travel, and the older display:contents workaround for that painted the bar
   under the content instead of over it. The wrapper is a child of the full-height content column, so
   it has room, and nothing is taken out of flow. --ri-head is the platform's own header height
   (60px on a published app, 0 when that header is transparent), measured by viz.platform_offset. */
div:has(> [class*="st-key-ws_head_"]){display:block!important;position:-webkit-sticky;position:sticky;
  top:var(--ri-head,0px);z-index:99999;background:#fff;margin-bottom:2px;
  border-bottom:1px solid #eef2f7;box-shadow:0 6px 12px rgba(15,23,42,.05)}
div[class*="st-key-ws_head_"]{background:#fff;padding:2px 0 2px;min-height:42px;
  border-bottom:none!important}
div[class*="st-key-ws_head_"] [data-testid="stHorizontalBlock"]{align-items:center}
.ri-wsid{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.ri-wsid .id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:800;font-size:19px;color:#0f172a}
.ri-wsid .chip{font-size:11.5px;font-weight:750;padding:2px 9px;border-radius:999px}
.ri-wsid .meta{font-size:12.5px;color:#64748b}
.ri-wsid .meta b{color:#0f172a}
.ri-wait{margin-left:4px;font-size:11.5px;color:#b45309;background:#fffbeb;border:1px solid #fde68a;
  border-radius:999px;padding:3px 9px;font-weight:650}
.ri-shead{display:flex;align-items:baseline;gap:10px;margin:2px 0 2px}
.ri-shead .t{font-size:15.5px;font-weight:750;color:#0f172a;letter-spacing:-.01em}
.ri-hint{font-size:12px;color:#64748b}
.ri-ask{display:flex;gap:10px;align-items:flex-start;border:1px solid #e5e7eb;border-left:4px solid #4f46e5;
  border-radius:10px;padding:9px 12px;margin:6px 0;background:#fff}
.ri-ask.done{border-left-color:#16a34a;background:#f8fafc;opacity:.85}
.ri-ask .who{font-weight:700;color:#0f172a;font-size:12.5px}
.ri-ask .what{font-size:12.5px;color:#334155}
.ri-ask .meta{font-size:11px;color:#64748b;margin-top:2px}
/* list rows: a real clickable row, not a dataframe cell */
div[class*="st-key-listrow-"] button{width:100%!important;text-align:left!important;justify-content:flex-start!important;
  height:auto!important;background:transparent!important;border:1px solid transparent!important;
  border-bottom:1px solid #eef2f7!important;border-radius:8px!important;padding:8px 10px!important;
  box-shadow:none!important}
div[class*="st-key-listrow-"] button:hover{background:#f8fafc!important;border-color:#e5e7eb!important}
div[class*="st-key-listrow-"] button>div{width:100%!important;justify-content:flex-start!important}
div[class*="st-key-listrow-"] button .stMarkdownEllipsis p{width:100%!important;text-align:left!important}
div[class*="st-key-listrow-"] button .stMarkdownEllipsis{width:100%!important;text-align:left!important;
  overflow:visible!important;text-overflow:clip!important;white-space:normal!important}
div[class*="st-key-listrow-"] button p,div[class*="st-key-listrow-"] button .stMarkdownEllipsis{
  width:100%!important;text-align:left!important;white-space:normal!important;overflow:visible!important}
.ri-lr .body{font-weight:600;font-size:13.5px;color:#0f172a}

div[class*="st-key-nav_"] button{justify-content:flex-start!important;font-weight:600!important}
.ri-sidecounts{display:flex;gap:10px;flex-wrap:wrap;font-size:11.5px;color:#64748b;margin:-2px 0 10px}
.ri-sidecounts b{color:#0f172a;font-weight:800}
/* --- cards: the label wrapper Streamlit adds must span the row, not centre itself (v77) --- */
div[class*="st-key-boardcard-"] button>div,
div[class*="st-key-attn-"] button>div{width:100%!important;justify-content:flex-start!important}
div[class*="st-key-boardcard-"] button .stMarkdownEllipsis,
div[class*="st-key-attn-"] button .stMarkdownEllipsis{width:100%!important;text-align:left!important;
  overflow:visible!important;text-overflow:clip!important;white-space:normal!important}
div[class*="st-key-boardcard-"] button .stMarkdownEllipsis p,
div[class*="st-key-attn-"] button .stMarkdownEllipsis p{width:100%!important;text-align:left!important}
div[class*="st-key-nav_"] button p{font-size:13.5px!important}
/* ---- v100 story layer: one type scale, one spacing grid, one accent ------------------------- */
:root{--ri-fs-xs:11px;--ri-fs-s:12.5px;--ri-fs-m:14px;--ri-fs-l:19px;--ri-fs-xl:30px;
  --ri-sp-1:4px;--ri-sp-2:8px;--ri-sp-3:14px;--ri-sp-4:22px}
.ri-hero3{display:grid;grid-template-columns:minmax(0,1.28fr) minmax(0,0.72fr) minmax(0,1fr);
  gap:var(--ri-sp-3);margin:0 0 2px;padding:0}
.ri-hero3 .f{min-width:0}
.ri-hero3 .k{font-size:var(--ri-fs-xs);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ri-muted);font-weight:700}
.ri-hero3 .v{font-size:clamp(20px,1.75vw,26px);line-height:1.15;font-weight:800;
  letter-spacing:-.02em;margin:2px 0 3px;overflow-wrap:normal;word-break:normal}
.ri-hero3 .n{font-size:var(--ri-fs-s);color:var(--ri-muted);overflow-wrap:anywhere}
@media (max-width:900px){.ri-hero3{grid-template-columns:1fr;gap:var(--ri-sp-2)}}
.ri-chain{display:flex;align-items:stretch;gap:6px;flex-wrap:wrap;
  margin:0 0 2px}
.ri-hop{flex:0 1 auto;min-width:150px;border:1px solid var(--ri-line);border-radius:10px;
  background:#fff;padding:5px 11px}
.ri-hop .d{font-size:var(--ri-fs-xs);text-transform:uppercase;letter-spacing:.05em;
  color:var(--ri-muted);font-weight:700}
.ri-hop .l{font-size:var(--ri-fs-m);font-weight:750;color:var(--ri-ink);margin:1px 0 2px;
  overflow-wrap:anywhere}
.ri-hop .e{font-size:var(--ri-fs-xs);color:var(--ri-muted)}
.ri-hop .s{display:block;font-size:var(--ri-fs-xs);color:#b45309;font-weight:650;margin-top:2px}
.ri-hop.holder{border-color:var(--ri-accent);box-shadow:inset 0 0 0 1px var(--ri-accent);
  background:#eef2ff}
.ri-hop.holder .l{color:#3730a3}
.ri-hop .now{display:inline-block;font-size:10.5px;font-weight:750;color:#fff;background:var(--ri-accent);
  border-radius:999px;padding:1px 7px;margin-left:6px;vertical-align:1px}
.ri-hoplink{align-self:center;color:#94a3b8;font-size:18px;line-height:1;padding:0 2px}
.ri-askcard{border:1px solid var(--ri-line);border-radius:10px;padding:5px 12px;
  background:#fff}
.ri-askcard .top{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.ri-askcard .who{font-weight:750;font-size:var(--ri-fs-m);color:var(--ri-ink)}
.ri-askcard .what{font-size:var(--ri-fs-s);color:#334155}
.ri-askcard .meta{font-size:var(--ri-fs-xs);color:var(--ri-muted);margin-top:4px}
.ri-askcard .travel{font-size:var(--ri-fs-xs);color:#475569;margin-top:5px;
  border-top:1px dashed var(--ri-line);padding-top:5px}
.ri-st{display:inline-block;font-size:10.5px;font-weight:750;letter-spacing:.03em;
  text-transform:uppercase;border-radius:999px;padding:2px 8px;border:1px solid}
.ri-st.sent{color:#475569;border-color:#94a3b8;border-style:dashed;background:#f8fafc}
.ri-st.acknowledged{color:#0f766e;border-color:#5eead4;background:#f0fdfa}
.ri-st.overdue{color:#b91c1c;border-color:#fca5a5;background:#fef2f2}
.ri-st.answered{color:#166534;border-color:#86efac;background:#f0fdf4}
.ri-st.reopened{color:#b45309;border-color:#fcd34d;background:#fffbeb}
.ri-unsent{display:inline-block;font-size:10px;font-weight:700;color:#64748b;border:1px dashed #cbd5e1;
  border-radius:6px;padding:1px 6px;margin-left:6px}
.ri-accel-inline{font-size:12px;margin:2px 0 4px;line-height:1.5}
.ri-accel{display:flex;flex-wrap:wrap;gap:var(--ri-sp-4);margin:var(--ri-sp-1) 0 var(--ri-sp-3)}
.ri-accel .f{min-width:210px}
.ri-accel .k{font-size:var(--ri-fs-xs);text-transform:uppercase;letter-spacing:.05em;
  color:var(--ri-muted);font-weight:700}
.ri-accel .v{font-size:var(--ri-fs-l);font-weight:800;color:var(--ri-ink);margin:1px 0 2px}
.ri-accel .n{font-size:var(--ri-fs-xs);color:var(--ri-muted);max-width:44ch}
.ri-inherit{border:1px solid #c7d2fe;background:#eef2ff;border-radius:var(--ri-r);
  padding:12px 16px;margin:6px 0 10px}
.ri-inherit .t{font-size:var(--ri-fs-xs);font-weight:800;color:#3730a3;text-transform:uppercase;
  letter-spacing:.05em}
.ri-inherit .c{font-size:var(--ri-fs-m);font-weight:700;color:var(--ri-ink);margin:4px 0 2px}
.ri-inherit .m{font-size:var(--ri-fs-xs);color:var(--ri-muted)}
.ri-inherit ol{margin:6px 0 0 18px;padding:0;font-size:var(--ri-fs-s);color:#334155}
.ri-inherit li{margin:2px 0}
/* ---- v101 Ask: the answer card (interpretation → number → query → basis) --------------------- */
.ri-answer{border:1px solid #c7d2fe;border-left:4px solid var(--ri-accent);border-radius:var(--ri-r);
  background:#fff;padding:12px 16px;margin:8px 0 6px}
.ri-answer.refused{border-color:var(--ri-line);border-left-color:#94a3b8}
.ri-answer .q{font-size:var(--ri-fs-xs);color:var(--ri-muted);font-style:italic}
.ri-answer .i{font-size:var(--ri-fs-s);color:#334155;margin:4px 0 6px}
.ri-answer .h{font-size:26px;font-weight:800;color:var(--ri-ink);line-height:1.15}
.ri-answer .n{font-size:var(--ri-fs-xs);color:var(--ri-muted);font-weight:600;margin-left:9px}
.ri-answer .p{font-size:var(--ri-fs-s);color:#334155;margin:5px 0}
.ri-answer .b{font-size:10.5px;color:var(--ri-muted);margin-top:7px;border-top:1px dashed var(--ri-line);
  padding-top:5px}
.ri-cite{font-size:11px;color:#475569;margin:1px 0 0 2px}
/* ---- v102 Who's on it: static agent panel ----------------------------------------------- */
.ri-agents .hd{display:flex;align-items:center;gap:8px;font-size:15.5px;font-weight:750;
  color:var(--ri-ink);margin:6px 0 4px}
.ri-simchip{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;
  border:1px solid #f59e0b;color:#92400e;background:#fffbeb;border-radius:999px;padding:2px 8px}
.ri-ablock{border:1px solid var(--ri-line);border-left:3px solid var(--ri-accent);border-radius:10px;
  padding:9px 13px;margin:6px 0;background:#fff}
.ri-ablock.draft{border-left-color:#0d9488;background:#f8fafc}
.ri-ablock .t{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ri-muted);
  font-weight:800}
.ri-ablock .d{font-size:13.5px;color:var(--ri-ink);font-weight:650;margin:3px 0 4px}
.ri-ablock .s{font-size:12px;color:#475569}
.ri-ablock .m{font-size:11px;color:var(--ri-muted);margin-top:4px}
.ri-factchip{display:inline-block;font-size:11px;color:#334155;background:#f8fafc;
  border:1px solid var(--ri-line);border-radius:999px;padding:2px 8px;margin:3px 4px 0 0}
.ri-rung .p{display:inline-block;font-size:11.5px;font-weight:700;border:1px solid var(--ri-line);
  border-radius:999px;padding:3px 10px;margin-right:6px;color:#64748b}
.ri-rung .p.on{background:var(--ri-accent);border-color:var(--ri-accent);color:#fff}
.ri-notsent{font-size:10.5px;font-weight:750;color:#92400e;border:1px dashed #fcd34d;
  background:#fffbeb;border-radius:6px;padding:1px 7px;margin-left:6px}
/* ---- v106 progressive disclosure: accordion headers, preview drawer ----------------------- */
div[class*="st-key-acc_"] button{width:100%!important;justify-content:flex-start!important;
  text-align:left!important;background:#fff!important;border:1px solid var(--ri-line)!important;
  border-left:3px solid #cbd5e1!important;border-radius:8px!important;padding:0 10px!important;min-height:22px!important;
  font-weight:600!important;font-size:12px!important;color:#0f172a!important;box-shadow:none!important}
div[class*="st-key-acc_"] button:hover{background:#f8fafc!important;border-left-color:var(--ri-accent)!important}
div[class*="st-key-acc_"] button p{font-size:12px!important;line-height:1.15!important;text-align:left!important;
  width:100%!important;white-space:normal!important}
div[class*="st-key-acc_"] button>div{width:100%!important;justify-content:flex-start!important}
.ri-drawer{border:1px solid #c7d2fe;border-radius:var(--ri-r);background:#fff;padding:14px 16px}
.ri-drawer .id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:800;font-size:17px}
.ri-drawer .t{font-size:13.5px;color:#0f172a;font-weight:650;margin:2px 0 8px}
.ri-drawer .f{border-top:1px solid var(--ri-line);padding:6px 0}
.ri-drawer .k{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ri-muted);font-weight:700}
.ri-drawer .v{font-size:15px;font-weight:750;color:var(--ri-ink)}
.ri-drawer .n{font-size:11.5px;color:var(--ri-muted)}
/* v106: the accordion is a list, not a stack of cards — tight gaps, one line each */
div[class*="st-key-acc_group_"] [data-testid="stVerticalBlock"]{gap:2px!important}
div[class*="st-key-acc_group_"] [data-testid="stVerticalBlockBorderWrapper"]{padding:2px 0!important}
/* v106: one tight stack on the incident screen — the page is a list, not a deck of cards */
[data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"]{gap:6px!important}
div[class*="st-key-ws_panel_"]{padding:2px 8px!important}
/* ---- v107a: one header row, four instrument tiles, six tabs ------------------------------- */
.ri-hdr{display:flex;align-items:center;gap:10px;flex-wrap:nowrap;overflow:hidden;white-space:nowrap}
.ri-hdr .id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:800;font-size:16px}
.ri-hdr .t{font-size:12.5px;color:#475569;overflow:hidden;text-overflow:ellipsis;max-width:38ch}
.ri-hdr .pill{font-size:10.5px;font-weight:750;border:1px solid var(--ri-line);border-radius:999px;
  padding:1px 8px;color:#334155;background:#f8fafc}
.ri-hdr .q{font-size:11px;color:var(--ri-muted);margin-left:auto}
.ri-hdr .clock{font-size:13px;font-weight:800;color:#0f172a}
.ri-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:2px 0 10px}
.ri-tile{border:1px solid var(--ri-line);border-radius:10px;background:#fff;padding:6px 10px 2px;
  min-height:92px;display:flex;flex-direction:column}
.ri-tile .k{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--ri-muted);font-weight:800}
.ri-tile .v{font-size:19px;font-weight:800;color:var(--ri-ink);line-height:1.15;margin-top:1px}
.ri-tile .q{font-size:10.5px;color:var(--ri-muted)}
.ri-tile .g{margin-top:auto;height:40px;display:flex;align-items:center}
div[class*="st-key-tabbody_"]{max-height:224px;overflow:hidden}
/* v107b: an underline strip, not pills — the mockup's tab bar */
div[class*="st-key-tab_"] button{background:transparent!important;border:none!important;
  border-bottom:2px solid transparent!important;border-radius:0!important;box-shadow:none!important;
  justify-content:flex-start!important;padding:3px 2px!important;min-height:34px!important;
  align-items:flex-start!important}
div[class*="st-key-tab_"] button p{font-size:11px!important;line-height:1.2!important;
  white-space:normal!important;color:#475569!important}
div[class*="st-key-tab_"] button[data-testid="stBaseButton-primary"]{border-bottom-color:var(--ri-accent)!important}
div[class*="st-key-tab_"] button[data-testid="stBaseButton-primary"] p{color:var(--ri-accent)!important;font-weight:750!important}
div[class*="st-key-tab_"] button:hover{background:transparent!important;border-bottom-color:#c7d2fe!important}
.ri-hdr .t{max-width:26ch}
/* ---- v108: concept A — breadcrumb header, four tiles, graph hero, tabs --------------------- */
.ri-h2 .l{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ri-muted);font-weight:800}
.ri-h2 .row{display:flex;align-items:center;gap:10px;overflow:hidden;white-space:nowrap}
.ri-h2 .t{font-size:19px;font-weight:800;letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis}
.ri-h2 .r{margin-left:auto;display:flex;align-items:center;gap:8px}
.ri-h2 .pill{font-size:10.5px;font-weight:750;border:1px solid var(--ri-line);border-radius:999px;padding:1px 8px}
.ri-h2 .q{font-size:11px;color:var(--ri-muted)}
.ri-h2 .clock{font-size:13px;font-weight:800}
.ri-card2{border:1px solid var(--ri-line);border-radius:12px;background:#fff;padding:8px 12px}
.ri-card2 .h{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--ri-muted);font-weight:800;margin-bottom:4px}
.ri-card2 .cap{font-size:11px;color:#334155;border-top:1px solid var(--ri-line);padding-top:5px;margin-top:2px}
.ri-card2 .legendline{display:flex;gap:14px;font-size:10px;color:var(--ri-muted);margin-top:4px}
.ri-card2 .legendline i{display:inline-block;width:16px;height:0;border-top:2px solid #475569;
  vertical-align:3px;margin-right:4px}
.ri-card2 .legendline i.dash{border-top:2px dashed #b45309}
.ri-card2 .legendline .n{margin-left:auto}
.ri-card2 .big{font-size:12.5px;font-weight:650;color:var(--ink);line-height:1.4}
.ri-card2 .nextbox{border:1px solid #c7d2fe;background:#eef2ff;border-radius:10px;padding:7px 10px;margin-top:8px}
.ri-card2 .nextbox .l{font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;color:#3730a3;font-weight:800}
.ri-card2 .nextbox .a{font-size:12.5px;font-weight:650;color:#1e1b4b;margin-top:2px}
.ri-card2 .who{display:flex;align-items:center;gap:8px;margin-top:5px;font-size:11.5px}
.ri-card2 .who .av{width:22px;height:22px;border-radius:50%;background:#e5e7eb;display:flex;align-items:center;
  justify-content:center;font-size:9.5px;font-weight:800;color:#334155}
.ri-card2 .who b{display:block;font-weight:700;color:var(--ink)}
.ri-card2 .who i{display:block;font-style:normal;font-size:10px;color:var(--ri-muted)}
.ri-card2 .who em{margin-left:auto;font-style:normal;font-size:10px;color:var(--ri-muted)}
.ri-tile{min-height:64px!important;padding:4px 10px!important;height:auto!important;overflow:hidden}
.ri-tile .v{font-size:17px!important}
.ri-tile .g{height:20px!important}
div[class*="st-key-tabbody_"]{max-height:144px;overflow:hidden}
@media (max-width:1320px){
  div[class*="st-key-tab_"] button p{font-size:9.5px!important;line-height:1.15!important}
  .ri-h2 .t{font-size:17px}
}
.ri-h2 .t{font-size:18px}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def platform_offset():
    """Measure Streamlit's own header and publish --ri-head / --ri-offset.

    A published app draws a 60px header (Fork / source) above the content with a six-digit z-index, so
    a bar pinned at top:0 hides underneath it. The height is measured rather than hardcoded, and only
    counted when that header is actually opaque: a local dev header is transparent, and pinning below
    it would leave a strip of live content above the bar.

    --ri-offset is what a jump target uses so it lands just below the pinned bar, not under it. Runs
    through components.html because a component iframe re-executes its script on every rerun.
    """
    import streamlit.components.v1 as components
    components.html(
        "<script>(function(){try{var w=window.parent,d=w.document;"
        "function hdr(){var h=d.querySelector('[data-testid=\"stHeader\"]');if(!h)return 0;"
        "var cs=d.defaultView.getComputedStyle(h);var bg=cs.backgroundColor||'';"
        "var m=bg.match(/rgba?\\(([^)]+)\\)/);"
        "var a=m?(m[1].split(',').length>3?parseFloat(m[1].split(',')[3]):1):1;"
        "if(a<0.2)return 0;return h.getBoundingClientRect().height;}"
        "function place(){var bar=d.querySelector('[class*=\"st-key-ws_head_\"]');"
        "var hh=hdr();var bh=bar?bar.offsetHeight:52;var root=d.documentElement.style;"
        "root.setProperty('--ri-head',hh+'px');"
        "root.setProperty('--ri-offset',(hh+bh+14)+'px');}"
        "if(!w.__riBar){w.__riBar=place;w.addEventListener('resize',place);}"
        "w.__riBar=place;place();setTimeout(place,150);setTimeout(place,700);setTimeout(place,1600);"
        "}catch(e){}})();</script>", height=0)


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


# ---------------------------------------------------------------- phases (v99)
# Eight stages is too many to read on a projector. The stepper shows four phases; the stage the
# incident is actually in is named inside the active phase. The stages themselves are untouched —
# they are what the data, the audit trail and the OLAs record.
PHASES = ["Detect", "Resolve", "Act & Verify", "Close & Learn"]
PHASE_OF = {"Detect": "Detect",
            "Triage": "Resolve", "Investigate": "Resolve", "Correlate": "Resolve",
            "Act": "Act & Verify", "Verify": "Act & Verify",
            "Close": "Close & Learn", "Learn": "Close & Learn"}


def phase_of(stage):
    return PHASE_OF.get(stage, PHASES[0])


def stages_in_phase(phase):
    return [s for s in RESOLUTION_FLOW if PHASE_OF.get(s) == phase]


def phase_stepper(stage):
    """Four phase chips; the active one carries the stage name inside it."""
    phase = phase_of(stage)
    idx = PHASES.index(phase)
    html = ['<div class="ri-flow">']
    for i, p in enumerate(PHASES):
        cls = "done" if i < idx else ("current" if i == idx else "todo")
        inner = p
        if i == idx:
            inner = (f'{p}<span class="ri-substep">{stage}</span>')
        html.append(f'<span class="ri-step {cls}">{inner}</span>')
        if i < len(PHASES) - 1:
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


RESOLUTION_FLOW = ["Detect", "Triage", "Investigate", "Correlate", "Act", "Verify", "Close", "Learn"]


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


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def hypothesis_cards(hyps, total=None, offset=0):
    """Render RCA hypotheses as visual cards with confidence bars, badges and evidence.

    The rank is printed from the SAME ordered list the cards come from, so a low-confidence signal
    can never be presented as if it were near the top: the competing DB signal reads
    "ranked 4th of 4 · low · 30%"."""
    total = total or (offset + len(hyps))
    for i, h in enumerate(hyps):
        rank = offset + i + 1
        conf = h.get("confidence", "low")
        pct = CONF_PCT.get(conf, 30)
        col = CONF_COLOR.get(conf, "#94a3b8")
        confirmed = h.get("status") == "confirmed"
        badge = "CONFIRMED" if confirmed else "SUSPECTED"
        badgecol = "#16a34a" if confirmed else "#d97706"
        bg = "#f0fdf4" if confirmed else "#ffffff"
        _kind = (h.get("type") or "").title()
        icon = (f'<span style="font-size:10.5px;font-weight:700;letter-spacing:.04em;color:#64748b;'
                f'text-transform:uppercase">{_kind} · </span>') if _kind else ""
        top = ('<span style="background:#4f46e5;color:#fff;font-size:10px;font-weight:700;'
               'padding:2px 8px;border-radius:999px;margin-left:8px">MOST LIKELY</span>') if rank == 1 else ""
        st.markdown(
            f'<div style="border:1px solid #e5e7eb;border-left:7px solid {col};border-radius:12px;'
            f'padding:12px 15px;margin:9px 0;background:{bg};box-shadow:0 1px 2px rgba(0,0,0,.05)">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a">{icon} '
            f'{h.get("label") or h.get("type","").title()}'
            f'{top}<div style="font-weight:500;color:#334155;margin-top:3px">{h.get("text","")}</div></div>'
            f'<div style="text-align:right;white-space:nowrap">'
            f'<span style="background:{badgecol};color:#fff;font-weight:700;font-size:11px;'
            f'padding:3px 10px;border-radius:999px">{badge}</span>'
            f'<div style="font-size:11px;color:#64748b;margin-top:5px">ranked {_ordinal(rank)} of {total}</div>'
            f'</div></div>'
            f'<div style="margin:9px 0 3px"><div style="height:8px;background:#e5e7eb;border-radius:999px;'
            f'overflow:hidden"><div style="height:8px;width:{pct}%;background:{col};border-radius:999px">'
            f'</div></div><div style="font-size:12px;color:#64748b;margin-top:4px">confidence: '
            f'<b>{conf}</b> ({pct}%) · ranked {_ordinal(rank)} of {total}</div></div>'
            f'<div style="font-size:12.5px;color:#475569"><b>Evidence</b> · {h.get("evidence","")}</div>'
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
        ts = str(r.get("ts", ""))
        tshow = ts[11:16] if len(ts) >= 16 else ts
        html.append(
            f'<div class="ri-tl-item"><span class="ri-tl-dot" style="background:{col};'
            f'box-shadow:0 0 0 2px {col}"></span>'
            f'<div style="font-size:12px;color:#64748b">{tshow}</div>'
            f'<div style="margin-top:3px"><span class="ri-tl-kind" style="background:{col}">{r["kind"].title()}</span>'
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
    ("Status", [("assigned", "#d97706"), ("accepted", "#0891b2"), ("reopened", "#b91c1c"),
                ("done", "#16a34a")]),
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


# ------------------------------------------------------------------ the story layer (v100)
def hero_strip(facts):
    """Three facts, one line each, large, no decoration — the first three seconds of the incident.

    `facts` is story.hero()["facts"]: label, value, note, tone. A value the record cannot support
    arrives already as an em dash with a note saying why, so nothing here has to invent one."""
    cells = []
    for f in facts:
        cells.append(
            f'<div class="f"><div class="k">{html.escape(str(f["label"]))}</div>'
            f'<div class="v" style="color:{f.get("tone") or "#0f172a"}">'
            f'{html.escape(str(f["value"]))}</div>'
            f'<div class="n">{html.escape(str(f.get("note") or ""))}</div></div>')
    st.markdown(f'<div class="ri-hero3">{"".join(cells)}</div>', unsafe_allow_html=True)


def domain_chain(nodes):
    """A handoff you can see: domain chips joined by arrows, the current holder highlighted, and
    the time each hop has taken printed on the hop itself (not summarised into a badge)."""
    if not nodes:
        st.caption("No handoff recorded — this incident has stayed in one domain.")
        return
    parts = []
    for i, n in enumerate(nodes):
        if i:
            parts.append('<div class="ri-hoplink" aria-hidden="true">→</div>')
        now = '<span class="now">now</span>' if n.get("holder") else ""
        stale = (f'<span class="s">{html.escape(str(n["stale"]))}</span>'
                 if n.get("stale") else "")
        parts.append(
            f'<div class="ri-hop{" holder" if n.get("holder") else ""}"'
            f' title="{html.escape(str(n.get("hint") or ""))}">'
            f'<div class="d">{html.escape(str(n.get("domain") or n.get("kind") or ""))}</div>'
            f'<div class="l">{html.escape(str(n.get("label") or ""))}{now}</div>'
            f'<div class="e">{html.escape(str(n.get("clock") or ""))}</div>{stale}</div>')
    st.markdown(f'<div class="ri-chain">{"".join(parts)}</div>', unsafe_allow_html=True)


def request_card(r, travels, key):
    """One ask as a card: owner, ask, state, deadline — and what travels with it.

    The card body is plain HTML so it reads as one object; the single action (Chase) is a real
    Streamlit button beside it. `r` is a story.requests() row, `travels` the (stage, impact,
    evidence) it carries. `key` makes the button unique per request."""
    state = html.escape(str(r["state"]))
    if r.get("overdue"):
        when = f'{r["over_by"]}m over a {r["deadline_min"]}m deadline'
    else:
        when = f'{r["deadline_min"]}m deadline, not yet due'
    unsent = ('<span class="ri-unsent" title="No connector is configured — this is recorded, '
              'not delivered">not sent · simulated</span>') if not r.get("delivered") else ""
    stage, impact, evidence = travels
    st.markdown(
        f'<div class="ri-askcard"><div class="top">'
        f'<span class="who">{html.escape(str(r["owner"]))}</span>'
        f'<span class="what">{html.escape(str(r["ask"]))}</span>'
        f'<span class="ri-st {state}">{state}</span>{unsent}</div>'
        f'<div class="meta">{html.escape(when)} · asked by {html.escape(str(r["asked_by"]))} · '
        f'{html.escape(str(r["channel"]))} (recorded only)</div>'
        f'<div class="travel"><b>Travels with the ask</b> — stage {html.escape(str(stage))} · '
        f'{html.escape(str(impact))} · evidence {html.escape(str(evidence))}</div></div>',
        unsafe_allow_html=True)


def accel_row(items):
    """Measured durations on one compact line — an em dash with the reason when unsupported."""
    bits = []
    for label, value, note in items:
        dash = value in (None, "", "—")
        bits.append(f'<b>{html.escape(str(label))}</b> '
                    f'<span style="font-weight:800;color:{"#94a3b8" if dash else "#0f172a"}">'
                    f'{html.escape("—" if dash else str(value))}</span> '
                    f'<span style="color:#64748b">{html.escape(str(note or ""))}</span>')
    st.markdown(f'<div class="ri-accel-inline">{"  ·  ".join(bits)}</div>', unsafe_allow_html=True)


def inherit_block(inheritance):
    """What the next incident with this signature starts with — cause and runbook, before the record."""
    steps = "".join(f'<li>{html.escape(str(s))}</li>' for s in inheritance.get("runbook") or [])
    st.markdown(
        f'<div class="ri-inherit">'
        f'<div class="t">The next incident with this signature starts with this</div>'
        f'<div class="c">{html.escape(str(inheritance.get("root_cause") or "—"))}</div>'
        f'<div class="m">signature <b>{html.escape(str(inheritance.get("signature")))}</b>'
        f' · from {html.escape(str(inheritance.get("ref")))}'
        f' · {len(inheritance.get("runbook") or [])} step(s) that worked</div>'
        f'{"<ol>" + steps + "</ol>" if steps else ""}</div>',
        unsafe_allow_html=True)


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
    """Compact next-step card (the section label is provided by the collapsible around it)."""
    extra = " · ".join(x for x in (
        f"why: {why}" if why else "",
        f"target: {target}" if target else "",
        f"blast: {blast}" if blast else "",
        f"risk: {risk}" if risk else "",
    ) if x)
    st.markdown(
        f'<div class="ri-card" style="padding:9px 12px">'
        f'<div style="font-weight:700;color:#0f172a;font-size:13.5px">{action}</div>'
        f'<div style="font-size:11.5px;color:#334155;margin-top:2px">owner: <b>{owner}</b> · '
        f'gate: <b>{gate}</b></div>'
        + (f'<div style="font-size:11px;color:#64748b;margin-top:2px">{extra}</div>' if extra else "")
        + '</div>', unsafe_allow_html=True)


def hero(priority, inc_id, title, meta, sla_text, verdict, chips, sla_label="SLA remaining",
         sla_tone="bad"):
    tone = {"bad": "#fca5a5", "good": "#86efac", "neutral": "#e2e8f0"}.get(sla_tone, "#fca5a5")
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
        f'<div class="meta">{sla_label}</div>'
        f'<div style="font-size:26px;font-weight:800;color:{tone}">{sla_text}</div>'
        f'<div style="margin-top:6px">{chip_html}</div></div></div></div>',
        unsafe_allow_html=True)


def _vcls(value):
    """Value typography bucket — keeps identifiers on one line instead of breaking mid-word."""
    s = str(value)
    if len(s) <= 10:
        return ""
    return " sm" if len(s) <= 18 else " xs"


def kpi_row(items):
    """Fact tiles: list of (label, value, sub, color). Rendered as one responsive grid so a tile
    can never squeeze into a mid-word break (the old st.columns version did exactly that)."""
    cells = []
    for label, value, sub, color in items:
        sub_html = f'<div class="s">{sub}</div>' if sub else ""
        cells.append(
            f'<div class="ri-kpi" style="border-left-color:{color}">'
            f'<div class="l">{label}</div>'
            f'<div class="v{_vcls(value)}" title="{value}">{value}</div>{sub_html}</div>')
    st.markdown(f'<div class="ri-facts">{"".join(cells)}</div>', unsafe_allow_html=True)


def stage_head(stage, note=None):
    """A stage section header for the single-scroll incident screen: number, name, its phase."""
    n = RESOLUTION_FLOW.index(stage) + 1 if stage in RESOLUTION_FLOW else ""
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:9px;margin:18px 0 2px;'
        f'border-bottom:1px solid #e2e8f0;padding-bottom:4px">'
        f'<span style="font-size:11px;font-weight:700;color:#94a3b8">{n}</span>'
        f'<span style="font-size:16px;font-weight:700;color:#0f172a">{stage}</span>'
        f'<span style="font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;'
        f'color:#4f46e5">{phase_of(stage)}</span></div>', unsafe_allow_html=True)
    if note:
        st.caption(note)


def handshake(text):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:9px;background:#EEF2FF;border-left:4px solid '
        f'#4f46e5;padding:8px 12px;border-radius:8px;margin:2px 0 10px;font-size:13px">'
        f'<span><b>Handshake</b> — {text}</span></div>',
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
        f'<div style="font-weight:700;color:#0f172a;font-size:14px">Recommended action</div>'
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


SEV_LABEL = {"P1": ("", "Critical"), "P2": ("", "Major"), "P3": ("", "Minor"),
             "P4": ("", "Low")}


def board_card(inc, domain, verdict, on_click, args, stage=None, sla=None, open_=False, linked=False,
               prefix="boardcard"):
    """Compact incident row (Linear-style): line 1 = ID + title; line 2 = severity · status ·
    domain · owner · time. The whole row is clickable (keyed button styled as a card); the
    per-priority left border and the ⇄ marker carry severity and cross-domain at a glance."""
    pri = inc.get("priority", "P3")
    status = (inc.get("status") or "open").title()
    owner = inc.get("owner_team") or "—"
    mark = ""
    link = "⇄ " if linked else ""
    _, sev = SEV_LABEL.get(pri, ("", "Minor"))
    line1 = f'{mark}{link}**{inc["id"]}**  {inc["title"]}'
    stage_txt = stage or "—"
    line2 = f'{sev} · {status} · {stage_txt}'
    line3 = f'{sla} · {owner}' if sla else owner
    st.button(f'{line1}  \n{line2}  \n{line3}', key=f'{prefix}-{pri}-{inc["id"]}', width="stretch",
              on_click=on_click, args=args)


def list_row(inc, domain, verdict, on_click, args, stage=None, sla=None, waiting=None, linked=False,
             secondary=None):
    """One clickable incident row — dense like a table, but the whole row is the button.

    v106: the second line answers the queue questions before the click — who holds it and for how
    long, the SLA left, whether it crosses domains, and the next action. Richer row, not more
    columns. Selecting it opens the summary drawer."""
    pri = inc.get("priority", "P3")
    dot = {"P1": "🔴", "P2": "🟠", "P3": "🔵", "P4": "⚪"}.get(pri, "⚪")
    status = (inc.get("status") or "open").title()
    meta = secondary or " · ".join([b for b in (domain, stage, inc.get("owner_team"), status) if b])
    tail = []
    if waiting:
        tail.append(f'waiting **{waiting}**')
    if sla and status.lower() != "closed":
        tail.append(sla)
    if tail and not secondary:
        meta += "  ·  " + "  ·  ".join(tail)
    mark = "⇄ " if linked else ""
    label = f'{dot} **{mark}{inc["id"]}**  {inc["title"]}  \n{meta}'
    st.button(label, key=f'listrow-{inc["id"]}', width="stretch", on_click=on_click, args=args)


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


# ------------------------------------------------------------------ charts (v76)
LIVE_C = "#4f46e5"
BASE_C = "#94a3b8"
SOFT_C = "#c7d2fe"


def data_badge(kind="live"):
    """Honest provenance chip — the reader should never have to guess if a number is measured."""
    label, cls = ("Live data", "live") if kind == "live" else ("Illustrative", "illus")
    st.markdown(f'<span class="ri-prov {cls}"><span class="d"></span>{label}</span>',
                unsafe_allow_html=True)


def _axis(kind="N", **kw):
    cfg = dict(title=None, labelColor="#475569", titleColor="#64748b", labelFontSize=11,
               labelLimit=200, grid=kw.pop("grid", True))
    if kind == "N":
        cfg["labelAngle"] = 0
        cfg["grid"] = False
    return alt.Axis(**{**cfg, **kw})


def chart_style(chart, height=250):
    return (chart.properties(height=height, background="transparent")
            .configure_axis(labelColor="#475569", titleColor="#64748b", labelFontSize=11,
                            titleFontSize=11, gridColor="#eef2f7", domainColor="#e2e8f0",
                            tickColor="#e2e8f0", labelLimit=200)
            .configure_legend(labelColor="#475569", titleColor="#64748b", labelFontSize=11,
                              orient="top", direction="horizontal", symbolType="square",
                              symbolSize=110, offset=6)
            .configure_view(strokeWidth=0))


def chart_bars(df, xf, yf, *, group=None, sort=None, height=250, fmt="d", muted=False, labels=True):
    """Bar chart with value labels. Zero counts stay visible (label on the baseline) and the
    categorical axis keeps every category in the given order — no silent gaps."""
    base = dict(x=alt.X(f"{xf}:N", sort=sort, axis=_axis("N")),
                y=alt.Y(f"{yf}:Q", title=None, axis=alt.Axis(tickMinStep=1, labelColor="#475569",
                                                             gridColor="#eef2f7", domainColor="#e2e8f0")),
                tooltip=[alt.Tooltip(f"{xf}:N"), alt.Tooltip(f"{yf}:Q")])
    if group:
        base["xOffset"] = alt.X(f"{group}:N", sort=None)
        base["color"] = alt.Color(f"{group}:N", legend=alt.Legend(title=None),
                                  scale=alt.Scale(range=[BASE_C, LIVE_C]))
    else:
        base["color"] = alt.value(SOFT_C if muted else LIVE_C)
    bars = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(**base)
    if not labels:
        return chart_style(bars, height)
    text = dict(x=base["x"], y=alt.Y(f"{yf}:Q", title=None, stack=None),
                text=alt.Text(f"{yf}:Q", format=fmt))
    if group:
        text["xOffset"] = base["xOffset"]
    marks = alt.Chart(df).mark_text(dy=-7, fontSize=10.5, color="#475569").encode(**text)
    return chart_style(bars + marks, height)


def chart_lines(df, xf, yf, cf, *, sort=None, height=250, colors=(BASE_C, LIVE_C), width=2.2):
    chart = alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=55, filled=True),
                                    strokeWidth=width).encode(
        x=alt.X(f"{xf}:N", sort=sort, axis=_axis("N")),
        y=alt.Y(f"{yf}:Q", title=None, axis=alt.Axis(labelColor="#475569", gridColor="#eef2f7",
                                                     domainColor="#e2e8f0")),
        color=alt.Color(f"{cf}:N", legend=alt.Legend(title=None), scale=alt.Scale(range=list(colors))),
        tooltip=[alt.Tooltip(f"{xf}:N"), alt.Tooltip(f"{cf}:N"), alt.Tooltip(f"{yf}:Q")])
    return chart_style(chart, height)


# ------------------------------------------------------------------ shell + collab UI (v77)
def page_head(title, subtitle=None, right=None):
    """Consistent page header: title + one-line purpose, with an optional right-hand action row."""
    c1, c2 = st.columns([5.2, 1.8], vertical_alignment="bottom")
    with c1:
        st.markdown(f'<div class="ri-phead"><div class="t">{title}</div>'
                    + (f'<div class="s">{subtitle}</div>' if subtitle else "")
                    + "</div>", unsafe_allow_html=True)
    with c2:
        if right:
            right()


def crumb(text, on_click, args=(), key=None):
    """Small back-link above a workspace title."""
    slug = key or "".join(c if c.isalnum() else "_" for c in text.lower())[:24]
    st.button(f"← {text}", key=f"crumb_{slug}", on_click=on_click, args=args, type="tertiary")


def collab_chips(participants, waiting=None, limit=4):
    """Who is on the incident, and what the team is currently waiting on."""
    shown = list(participants)[:limit]
    chips = "".join(f'<span class="ri-person"><span class="ri-avatar">{viz_initials(p)}</span>'
                    f'<b>{p}</b></span>' for p in shown)
    extra = len(participants) - len(shown)
    if extra > 0:
        chips += f'<span class="ri-person"><b>+{extra}</b></span>'
    wait = f'<span class="ri-wait">{waiting}</span>' if waiting else ""
    st.markdown(f'<div class="ri-participants">{chips}{wait}</div>', unsafe_allow_html=True)


def viz_initials(name):
    """Two-letter monogram for a team or a person: 'Platform Engineering' → PE, 'Data observability' → DO."""
    words = [w for w in str(name).replace("(", " ").replace(")", " ").split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "•").upper()


def section(title, hint=None, right=None):
    """Uniform section heading so every block reads the same — no ad-hoc #### levels."""
    c1, c2 = st.columns([5, 1.4], vertical_alignment="center")
    with c1:
        extra = f'<span class="ri-hint">{hint}</span>' if hint else ""
        st.markdown(f'<div class="ri-shead"><span class="t">{title}</span>{extra}</div>',
                    unsafe_allow_html=True)
    with c2:
        if right:
            right()


# ------------------------------------------------------------------ closure gate (v78)
def closure_gate(state, on_close, actor="Incident Manager", expanded=False, asks=None,
                 on_done=None, prefix="gate"):
    """One place that says whether an incident may be closed — and what to do about it.

    Blocked items are actionable: an open request can be completed from here, and a missing or failed
    verification points at the step that fixes it. A gate that only refuses is a dead end."""
    if state["closed"]:
        st.markdown('<div class="ri-gate ok"><b>Closed</b> · kept read-only on the verified record</div>',
                    unsafe_allow_html=True)
        return
    if state["eligible"]:
        c1, c2 = st.columns([5, 1.4], vertical_alignment="center")
        c1.markdown('<div class="ri-gate ok"><b>Closure eligible</b> · independent verification passed '
                    'and no open requests</div>', unsafe_allow_html=True)
        if c2.button("Close incident", type="primary", width="stretch", key=f"{prefix}_close"):
            ok, msg = on_close()
            st.session_state["flash"] = msg
            st.rerun()
        return
    with st.expander(f'Closure blocked · {len(state["reasons"])} requirement(s) open', expanded=expanded):
        for r in state["reasons"]:
            st.markdown(f'- {r}')
        if asks:
            st.caption("Open requests are the last blocker — close them here:")
            for d in asks:
                c = st.columns([5.4, 1], vertical_alignment="center")
                c[0].markdown(f'**{d["to_"]}** · {d["action"]}')
                if c[1].button("Mark done", key=f"{prefix}_done_{d['id']}", width="stretch",
                               on_click=on_done, args=(d,)):
                    pass
        st.caption("Closure is gated on the authoritative verification record — a fix applied is not a "
                   "closure. Execution and independent verification live in **Act & verify (guided)**.")


# ------------------------------------------------------------------ Who's on it (v102)
def agent_panel_head(p):
    """Heading + orchestrator + specialist. The simulated chip is part of the heading, visible."""
    facts = "".join(f'<span class="ri-factchip">{html.escape(f["text"])}</span>'
                    for f in p["orchestrator"]["facts"])
    s = p["specialist"]
    sig = s["signal"]
    signal = ""
    if sig.get("score") is not None:
        signal = (f'<span class="ri-factchip" title="{html.escape(sig["label"])}">'
                  f'{sig["score"]:.2f} {html.escape(str(sig["basis"]))} signal</span>')
    st.markdown(
        f'<div class="ri-agents"><div class="hd">Who’s on it'
        f'<span class="ri-simchip">SIMULATED</span></div>'
        f'<div class="ri-ablock"><div class="t">Orchestrator · routing decision</div>'
        f'<div class="d">{html.escape(p["orchestrator"]["decision"])}</div>'
        f'<div class="s">{facts}</div></div>'
        f'<div class="ri-ablock"><div class="t">Specialist · {html.escape(s["agent"])}</div>'
        f'<div class="s">{html.escape(s["did"])}</div>'
        f'<div class="m">Reviewed <b>{s["reviewed"]}</b> signals · ranked <b>{s["ranked"]}</b> '
        f'leads · set aside <b>{s["rejected"]}</b> low-confidence lead(s) {signal}</div></div>',
        unsafe_allow_html=True)


def agent_panel_tail(p):
    """Handoff draft and the autonomy rung. The controls beside it are rendered by the caller."""
    h = p["handoff"]
    rung = "".join(
        f'<span class="p{" on" if r == p["rung"] else ""}">{html.escape(r)}'
        f'{" · highlighted" if r == p["rung"] else ""}</span>'
        for r in ("suggest", "draft", "act with approval"))
    st.markdown(
        f'<div class="ri-ablock draft"><div class="t">Handoff · draft ask'
        f'<span class="ri-notsent">NOT SENT</span></div>'
        f'<div class="d">{html.escape(h["to"])} — {html.escape(h["ask"])}</div>'
        f'<div class="m"><b>Stage</b> {html.escape(str(h["stage"]))} · '
        f'<b>Impact</b> {html.escape(str(h["impact"]))} · '
        f'<b>Evidence</b> {html.escape(str(h["evidence"]))}</div></div>'
        f'<div class="ri-ablock"><div class="t">Autonomy rung</div>'
        f'<div class="ri-rung">{rung}</div>'
        f'<div class="m">Static definition — no agent is running and nothing is sent.</div></div>'
        f'</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ progressive disclosure (v106)
def _toggle_section(ref, key):
    """Accordion: one open section per incident. Clicking the open header closes it."""
    cur = st.session_state.get(f"open_{ref}")
    st.session_state[f"open_{ref}"] = None if cur == key else key


def accordion_header(ref, key, title, detail="", badge="", tone="", is_open=False):
    """A section header that states what is inside, before it is opened.

    The badge (OVERDUE / UNVERIFIED / BLOCKED / READY) is part of the label, never hidden — a
    collapsed section must not conceal a critical fact."""
    arrow = "▾" if is_open else "▸"
    bits = [b for b in (badge, detail) if b]
    label = f'{arrow}  {title}' + (f'  ·  {bits[0]}' if bits else "")
    if len(bits) > 1:
        label += "  ·  " + "  ·  ".join(bits[1:])
    st.button(label, key=f"acc_{ref}_{key}", width="stretch",
              on_click=_toggle_section, args=(ref, key))


def drawer(inc, domain, verdict, facts, next_actor, blocker, on_open):
    """Right-hand summary: the hero facts for one incident, and one way in."""
    rows = "".join(
        f'<div class="f"><div class="k">{html.escape(k)}</div>'
        f'<div class="v">{html.escape(str(v))}</div>'
        f'<div class="n">{html.escape(str(n or ""))}</div></div>'
        for k, v, n in facts)
    st.markdown(
        f'<div class="ri-drawer"><div class="id">{html.escape(inc["id"])}</div>'
        f'<div class="t">{html.escape(inc.get("title") or "")}</div>'
        f'<div class="f"><div class="k">Verdict</div><div class="v">{html.escape(verdict)}</div>'
        f'<div class="n">{html.escape(domain)} · {html.escape(inc.get("priority") or "")}</div></div>'
        f'{rows}</div>', unsafe_allow_html=True)
    st.button("Open incident", type="primary", width="stretch",
              key=f"drawer_open_{inc['id']}", on_click=on_open, args=(domain, inc["id"]))
