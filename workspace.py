#!/usr/bin/env python3
"""Unified incident workspace — ONE layout shared by IT Ops and DataOps.

The chrome (hero header, the single clickable lifecycle, the cross-domain resolution thread,
the tabbed canvas and the activity rail) is identical everywhere. Domain-specific content
is supplied by adapters in command_center (IT vs DataOps), so users get one product with
different operational context — not two tools side by side."""
import streamlit as st
import viz

_LC_SYM = {"done": "✔", "current": "●", "blocked": "⏸", "failed": "✖", "todo": "○"}


def _toggle_stage(sel_key, value):
    """on_click callback — open a stage's detail, or close it if the same stage is clicked again."""
    if st.session_state.get(sel_key) == value:
        st.session_state.pop(sel_key, None)
    else:
        st.session_state[sel_key] = value


def _lifecycle_clickable(lifecycle, stage_key, stage_panel):
    """One clickable stage per lifecycle step. Selecting a stage reveals its detail (what happened,
    collaboration, acceleration) with a Close control — no duplicate lifecycle blocks."""
    cols = st.columns(len(lifecycle))
    sel_key = f"lc_stage_{stage_key}"
    for col, (title, status, detail, ola) in zip(cols, lifecycle):
        icon = viz.STAGE_ICON.get(title, "⬜")
        col.button(f"{icon} {title}", key=f"lcb_{stage_key}_{title}", width="stretch",
                   type=("primary" if status == "current" else "secondary"),
                   on_click=_toggle_stage, args=(sel_key, title))
    st.caption("Each stage has its own colour; the **active** stage is highlighted. Click a stage to see "
               "what happened, who collaborated, and the acceleration at that stage.")

    sel = st.session_state.get(sel_key)
    if sel:
        with st.container(border=True):
            c1, c2 = st.columns([9, 1])
            c1.markdown(f'**{sel} — stage detail**')
            if c2.button("✕", key=f"lcx_{stage_key}", width="stretch"):
                st.session_state.pop(sel_key, None)
                st.rerun()
            stage_panel(sel)


def render_workspace(hero_kwargs, lifecycle, edges, tabs, rail, thread_note=None, corr=None,
                     collab_banner=None, next_step_banner=None, stage_key=None, stage_panel=None):
    """Draw the shared workspace.

    hero_kwargs : dict for viz.hero (priority, inc_id, title, meta, sla_text, verdict, chips)
    lifecycle   : list of (title, status, detail, ola) — the ONE lifecycle (clickable stages)
    edges       : list of edge dicts for viz.thread_edges (cross-domain thread)
    tabs        : ordered {label: callable} rendered as the tabbed canvas
    rail        : callable rendering the right-hand activity rail
    corr        : optional correlation dict (adds the cross-domain link caption)
    collab_banner: optional callable rendered inside the collaboration disclosure
    next_step_banner: optional callable — the prominent recommended next step
    stage_key / stage_panel: incident key + callable(stage) for the click-to-open stage detail
    """
    viz.hero(**hero_kwargs)

    st.markdown("#### Resolution lifecycle")
    if stage_panel and stage_key:
        _lifecycle_clickable(lifecycle, stage_key, stage_panel)
    else:
        viz.lifecycle_strip(lifecycle)
        with st.expander("Lifecycle detail", expanded=False):
            viz.thread_spine(lifecycle)

    if next_step_banner:
        with st.expander("👉 Recommended next step", expanded=True):
            next_step_banner()

    # The cross-domain resolution thread is the product's focal object: prominent (open) when the
    # incident is cross-domain; collapsed when it is a single-domain incident.
    if edges:
        with st.expander("🔗 Cross-domain resolution thread", expanded=bool(corr)):
            viz.thread_edges(edges)
            if corr:
                st.caption(f'🔗 Thread links **{corr["other_domain"]} {corr["other_id"]}** · shared cause '
                           f'**{corr["shared_cause"]}**.')
            st.caption(thread_note or "**Observed** = a recorded signal/relationship. **Inferred** = a "
                                      "hypothesis to confirm. Multiple contributing causes are allowed.")

    main, r = st.columns([2.4, 1])
    with main:
        for label, fn in tabs.items():
            with st.expander(label, expanded=(label == "Overview")):
                fn()
    with r:
        rail()
