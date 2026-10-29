#!/usr/bin/env python3
"""The Ask box and its answer card — a grounded answer, never a guess.

The card has exactly four parts, in the order a sceptical reader checks them: the interpretation of
the question, the number (or the narrative) with its n, the query that was actually executed, and
the tables/definitions it rests on. A refusal uses the same card shape, so it reads as an answer and
not as an error.
"""
import datetime as dt
import html

import streamlit as st

import ask


def _esc(v):
    return html.escape(str(v))


def _when(ts):
    try:
        return dt.datetime.fromisoformat(str(ts)).strftime("%d %b %H:%M")
    except Exception:
        return str(ts or "")


def _submit(prefix):
    """Enter in the box submits, like the button — no form, so the box stays a plain field."""
    st.session_state[f"{prefix}_submit"] = True


def render(prefix="ask", label="Ask the record"):
    """Ask box + answer card + follow-up chips. `prefix` keeps two instances on different pages
    from sharing one widget key."""
    # A shareable link: ?ask=summarise+INC-8841 answers on load, so a demo URL demonstrates a question.
    try:
        url_q = st.query_params.get("ask")
    except Exception:
        url_q = None
    if url_q and st.session_state.get(f"{prefix}_url_asked") != url_q:
        st.session_state[f"{prefix}_url_asked"] = url_q
        st.session_state[f"{prefix}_q"] = url_q
        st.session_state[f"{prefix}_answer"] = ask.answer(url_q)
        st.session_state[f"{prefix}_question"] = url_q

    pending = st.session_state.pop(f"{prefix}_pending", None)
    if pending:
        st.session_state[f"{prefix}_q"] = pending

    c1, c2 = st.columns([5.4, 1.1], vertical_alignment="center")
    q = c1.text_input(label, placeholder="how many incidents were reported yesterday",
                      key=f"{prefix}_q", label_visibility="collapsed",
                      on_change=_submit, args=(prefix,))
    go = c2.button("Ask", type="primary", width="stretch", key=f"{prefix}_go")
    st.caption("Answered only from stored definitions — counts, handoffs, resolution time and "
               "incident threads. If it cannot compute the answer, it says so.")

    submitted = bool(st.session_state.pop(f"{prefix}_submit", False)) or bool(go)
    if submitted and (q or "").strip():
        st.session_state[f"{prefix}_answer"] = ask.answer(q)
        st.session_state[f"{prefix}_question"] = q

    res = st.session_state.get(f"{prefix}_answer")
    if not res:
        return
    _card(res, st.session_state.get(f"{prefix}_question") or q)

    chips = res.get("followups") or []
    if chips:
        cols = st.columns(len(chips))
        for i, text in enumerate(chips):
            if cols[i].button(text, key=f"{prefix}_chip_{i}", width="stretch"):
                st.session_state[f"{prefix}_pending"] = text
                st.rerun()


def _card(res, question):
    tone = "" if res.get("ok") else " refused"
    paras = "".join(f'<div class="p">{_esc(p)}</div>' for p in res.get("narrative") or [])
    cites = ""
    if res.get("cites"):
        rows = "".join(
            f'<div class="ri-cite">· {_esc(_when(c.get("ts")))} {_esc(c.get("detail") or "")}</div>'
            for c in res["cites"][:6])
        cites = f'<div class="p"><b>{_esc(res.get("cites_label") or "Events used")}</b>{rows}</div>'
    st.markdown(
        f'<div class="ri-answer{tone}">'
        f'<div class="q">{_esc(question)}</div>'
        f'<div class="i">{_esc(res["interpretation"])}</div>'
        f'<div class="h" style="color:{"#94a3b8" if res["headline"] == "—" else "#0f172a"}">'
        f'{_esc(res["headline"])}'
        f'<span class="n">{_esc(res.get("n_label") or "")}</span></div>'
        f'{paras}{cites}'
        f'<div class="b"><b>Based on</b> — {_esc(res.get("based_on") or "—")}</div>'
        f'</div>', unsafe_allow_html=True)

    if res.get("sql"):
        with st.expander("Show the query", expanded=False):
            st.code(res["sql"], language="sql")
            if res.get("params"):
                st.caption("Parameters — " + " · ".join(f'{k}={v}' for k, v in res["params"].items()))
            st.caption("This is the statement the answer executed against the session database.")
