#!/usr/bin/env python3
"""Unified incident workspace — ONE layout shared by IT Ops and DataOps.

The chrome (hero header, the single shared lifecycle, the cross-domain resolution thread,
the tabbed canvas and the activity rail) is identical everywhere. Domain-specific content
is supplied by adapters in command_center (IT vs DataOps), so users get one product with
different operational context — not two tools side by side."""
import streamlit as st
import viz


def render_workspace(hero_kwargs, lifecycle, edges, tabs, rail, thread_note=None, corr=None,
                     collab_banner=None):
    """Draw the shared workspace.

    hero_kwargs : dict for viz.hero (priority, inc_id, title, meta, sla_text, verdict, chips)
    lifecycle   : list of (title, status, detail, ola) for viz.thread_spine — the ONE lifecycle
    edges       : list of edge dicts for viz.thread_edges (cross-domain thread)
    tabs        : ordered {label: callable} rendered as the tabbed canvas
    rail        : callable rendering the right-hand activity rail
    corr        : optional correlation dict (adds the cross-domain link caption)
    collab_banner: optional callable rendered prominently under the lifecycle
    """
    viz.hero(**hero_kwargs)

    st.markdown("#### Resolution lifecycle")
    viz.lifecycle_strip(lifecycle)
    st.caption("✔ done · ● active · ⏸ blocked · ✖ failed · ○ not started — status is shown by symbol "
               "**and** text, never colour alone. Each stage carries an internal **OLA** (owner-team "
               "target), distinct from the customer **SLA** in the header.")
    with st.expander("Lifecycle detail — stages, OLA and next action", expanded=False):
        viz.thread_spine(lifecycle)

    if collab_banner or corr:
        with st.expander("🤝 Collaboration & handoffs", expanded=False):
            if collab_banner:
                collab_banner()
            if corr:
                st.caption(f'🔗 Thread links **{corr["other_domain"]} {corr["other_id"]}** · shared cause '
                           f'**{corr["shared_cause"]}**.')

    if edges:
        with st.expander("🔗 Cross-domain resolution thread", expanded=False):
            viz.thread_edges(edges)
            st.caption(thread_note or "**Observed** = a recorded signal/relationship. **Inferred** = a "
                                      "hypothesis to confirm. Multiple contributing causes are allowed.")

    main, r = st.columns([2.4, 1])
    with main:
        tab_objs = st.tabs(list(tabs.keys()))
        for tab, fn in zip(tab_objs, tabs.values()):
            with tab:
                fn()
    with r:
        rail()
