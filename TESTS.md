# Tests — how we know it works

Two layers, both runnable without a browser.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests -q          # 177 tests, ~34s
python3 scripts/layout_check.py http://localhost:8501   # layout audit, needs Chrome on :9222
python3 scripts/smoke.py            # deployment smoke test, ~5s
```

`scripts/smoke.py` is the check to run before claiming a deployment: imports every module, boots the
app headless through Streamlit's own harness, opens an incident, follows the URL, goes back to the
list and asserts the URL was cleared. It exits non-zero on the first failure.

## Layout audit (`scripts/layout_check.py`)

Playwright is **not installed** in this container (the npm package is absent and installing browsers
needs network). The audit is the same idea over the Chrome DevTools Protocol against the headless
Chrome already running on :9222: it loads each screen, then asserts in-page that

1. no two sibling cards/tiles overlap (intersection > 1px on both axes),
2. nothing overflows horizontally and the incident document does not scroll (`scrollHeight <=
   innerHeight`),
3. header → tiles → hero → tab strip → panes appear in that order with no vertical overlap,
4. each of the six tabs opens with non-empty content; on Timeline, Connections and Act & verify
   "Show all" opens the overlay and closes, while Requests must expand inside the pane (no modal,
   same pane height, a `1–8 of N` range, a live `?action=` link on every unfinished row) and
   Evidence & RCA lists every ranked lead in place with its Confirm / Reject / Set aside link.

Screens: incident × six tabs for INC-8841 and DOP-1001, the incidents list. One line of PASS/FAIL
per screen; exit code 1 on any failure.

Result at v121: 14 screens checked, 14 PASS on the deployed app.

## `tests/test_incident_actions.py` — the Requests tab (v110)

15 tests over a throwaway copy of the database. Rendering is checked on `incident_html.build()`;
each action is driven through the real app (`AppTest` + query params), then the record and the
re-rendered document are both read back.

| Test | Asserts |
|---|---|
| `test_every_row_offers_exactly_the_actions_its_state_allows` | each row carries only what its state allows: an unsent ask offers Send alone, a completed one offers nothing, the rest offer chase/done (+ ack while assigned) |
| `test_action_links_carry_the_view_they_were_clicked_from` | each href carries `tab=Requests`, `full` and `page`, and an action on page 2 lands back on page 2 |
| `test_create_ask_is_an_inline_form_with_the_four_fields` | owner, action, deadline, what travels with it — inline, no modal |
| `test_pagination_range_and_prev_next_in_place` | `1–8 of N` / `9–N of N`, prev/next are links, both branches live inside the pane |
| `test_page_out_of_range_clamps_to_the_last_page` | `?page=99` renders the last page, not an empty pane |
| `test_expanded_page_holds_eight_rows_and_the_preview_holds_four` | 8 rows a page, ≤4 in the preview |
| `test_header_overdue_count_equals_the_badges` | the header equals the overdue rows on the thread, and the badges summed over every page equal it too |
| `test_acknowledge_action_mutates_and_rerenders` | status → accepted, actor + changed_at + event recorded, flash names who/when, badge ACKNOWLEDGED |
| `test_mark_done_resolves_the_overdue_and_the_header_says_so` | last overdue resolved → header `none overdue`, no OVERDUE badge left |
| `test_create_ask_makes_a_not_sent_request_and_send_delivers_it` | ask stored NOT SENT with `expected in 45 min` and its bundle; Send sets sent_at and reveals Chase/Ack/Done |
| `test_send_is_refused_once_the_request_is_already_sent` | a second send raises and does not rewrite the first stamp |
| `test_chase_with_a_target_logs_it_against_that_request` | the comment names the request's owner |
| `test_a_stale_target_changes_nothing_and_says_so` | unknown target → stated refusal, record untouched |
| `test_an_ask_without_an_owner_creates_nothing` | empty form → nothing created, reason shown |
| `test_actions_land_back_on_the_same_tab_and_page` | tab/full/page survive the action, `action` is consumed |

## `tests/test_remediation_learn.py` — apply, verify, learn, reopen (v121)

13 tests. Each drives the app with an `?action=…` parameter and then asserts the record *and* the
re-rendered document.

| Test | Asserts |
|---|---|
| `test_apply_is_refused_before_approval_and_says_so` | the gate refuses, nothing is written, the flash states why |
| `test_approve_records_who_and_when` | approval stamped with actor + time, pane says "Remediation approved" |
| `test_apply_records_the_action_and_asks_for_verification` | applied stamp, `action_id` on the resolution record, verification offered, close still unoffered |
| `test_verify_records_the_verdict_from_the_checks` | verdict + checks persisted, flash counts passes |
| `test_verify_refuses_without_an_applied_action` | no record written, reason stated |
| `test_verdict_follows_the_checks_not_the_hope` | all pass → Verified, a fail → Recovery failed, pending → Inconclusive |
| `test_a_failed_verification_keeps_the_close_blocked` | a non-Verified verdict cannot close |
| `test_a_verified_incident_closes_then_reopens` | close → closed, reopen → open, closure stamp cleared |
| `test_reopen_refuses_when_the_incident_is_open` | reopen on an open incident refuses |
| `test_learn_save_writes_the_record_with_who_and_when` | learning saved with actor/time, pane shows it, header says saved |
| `test_learn_save_requires_a_root_cause` | empty form saves nothing |
| `test_the_learn_form_is_inline_and_prefilled` | inline form, four fields, pre-filled from the record |
| `test_the_act_and_verify_pane_names_every_phase` | Confirm cause / Apply / Verify / Close all present |

## `tests/test_rca_and_gate.py` — leads and the close gate (v111)

16 tests. Each action is driven through the app (`AppTest` + query params); the test then asserts the
record changed *and* the re-rendered document shows it.

| Test | Asserts |
|---|---|
| `test_the_rca_pane_lists_every_lead_with_rank_confidence_and_evidence` | every lead with `#rank`, confidence %, its evidence line and SUSPECTED; the tab header counts them |
| `test_a_lead_exposes_only_the_decisions_that_would_change_it` | three links per undecided lead, returning to the tab they were taken from |
| `test_confirm_lead_records_the_decision_without_moving_the_rank` | status confirmed, actor + time, `confirmed_cause`/`confirmed_at` set, rank unchanged, badge CONFIRMED with who/when |
| `test_confirm_lead_retires_the_unconfirmed_sentence` | "nobody has confirmed it yet" is replaced by the confirmed lead |
| `test_reject_lead_records_it_and_keeps_it_listed` | REJECTED with actor/time, still listed with its evidence, order unchanged |
| `test_set_aside_lead_records_it_as_parked` | SET ASIDE with actor/time, nothing confirmed |
| `test_rejecting_the_confirmed_lead_unconfirms_the_cause` | a rejected cause cannot stay confirmed; the unconfirmed sentence returns |
| `test_confirm_cause_names_the_confirmed_lead` | flash, thread comment and the control's own sub-line name the lead and its rank |
| `test_confirm_cause_with_no_lead_says_so` | no lead → the control and flash say nothing is named |
| `test_a_stale_lead_target_changes_nothing` | unknown lead key → stated refusal, no decision written |
| `test_the_gate_lists_each_blocker_with_the_tab_that_resolves_it` | one row per open requirement, the resolving tab linked, close is a refusal not a link |
| `test_clearing_the_requests_leaves_only_the_verification_blocker` | a resolved blocker disappears; the header count drops to 1 |
| `test_an_eligible_gate_offers_close_and_hides_the_blockers` | eligible → `?action=close`, no blocker rows, header `ready` |
| `test_closing_records_actor_and_time_and_leaves_the_open_queue` | status closed, `closed_at`, "Closed by X at HH:MM" on screen, no second close, header `closed` |
| `test_the_close_link_stays_blocked_while_any_requirement_is_open` | a blocked close is not a link and changes nothing |
| `test_the_dataops_thread_renders_its_own_leads_and_gate` | DOP-1001 shows its own two leads and its own gate |

## What is covered

### `tests/test_agents.py` — the v102 agent panel, against a throwaway copy of the database

| Test | Asserts |
|---|---|
| `test_each_defined_incident_renders_the_panel` | all four defined incidents render the panel, with the visible SIMULATED chip, NOT SENT and exactly one highlighted rung |
| `test_undefined_incident_shows_a_neutral_empty_state` | an undefined incident invents nothing |
| `test_panel_numbers_equal_the_record` | wait, holder, SLA, domains, handoffs, stage and signal weight equal the record |
| `test_inc_8841_shows_the_ledger_signal_at_0_72_inferred` | the ledger signal is 0.72 inferred on INC-8841 |
| `test_a_changed_record_changes_the_panel` | moving a request's clock changes the panel's waiting figure |
| `test_facts_are_rendered_into_the_panel_text` | evidence chips come from the record, not the JSON |
| `test_only_defined_incidents_have_a_panel` | four definitions, and at least one incident left undefined |
| `test_agents_page_lists_six_rows_one_live` | six rows, one live, each states what it may do |

### `tests/test_ask.py` — the v101 Ask box

| Test | Asserts |
|---|---|
| `test_supported_question_parses_and_answers` (19 cases) | intent, answer and n for every supported question, each number against an independent SQL count |
| `test_unsupported_question_refuses_without_a_number` (7 cases) | refusal, no number, three examples offered |
| `test_count_uses_the_analytics_definition` | the Ask count is `analytics.created_between` |
| `test_median_uses_the_analytics_mttr_definition` | the Ask median is `analytics.mttr_between` |
| `test_the_query_shown_is_the_query_executed` | the displayed SQL runs and returns exactly the printed n |
| `test_no_answer_comes_from_prose` | every answer carries a number or cited events |
| `test_summary_tells_the_thread_in_order` | raise → signals → holder → unblocked → end, citations in order |
| `test_held_longest_names_the_domain_and_its_minutes` | the domain and minutes match `analytics.held_by_domain` |
| `test_ask_box_renders_on_incidents_and_analytics` | the box is present on both pages |

### `tests/test_story.py` — the v100 story layer, against a throwaway copy of the database

| Test | Asserts |
|---|---|
| `test_hero_waiting_is_the_oldest_open_request` | the hero's waiting clock and name are that request's own |
| `test_hero_sla_matches_the_priority_clock` | the SLA figure is the priority target minus elapsed |
| `test_hero_cross_domain_counts_match_the_record` | 3 domains = distinct chain domains; 2 handoffs = stored requests |
| `test_hero_strip_on_screen_matches_the_module` | the rendered strip prints exactly what `story.hero()` computes |
| `test_hero_is_honest_when_nothing_is_open` | a closed incident says closed, not a running clock |
| `test_chain_marks_the_current_holder_and_times_each_hop` | one holder, highlighted, with its own clock |
| `test_a_closed_incident_clock_stops_at_closure` | closure stops the clock (40m, not 6d) |
| `test_request_card_state_follows_the_recorded_transition` | sent → acknowledged → answered, never a claimed delivery |
| `test_request_card_states_are_designed` | every state has a designed label and colour |
| `test_acceleration_values_come_from_timestamps` | 4m and 18m are recomputed from the rows |
| `test_acceleration_is_an_em_dash_when_the_record_cannot_support_it` | unsupported → `—` on screen, not a guess |
| `test_inheritance_names_the_cause_and_the_runbook` | Learn inheritance carries cause + steps |
| `test_incident_page_has_no_placeholder_copy` | no TODO/lorem/coming-soon on screen |

### `tests/test_navigation.py` — end-to-end, drives the real `app.py` via `streamlit.testing.v1.AppTest`

| Test | Asserts |
|---|---|
| `test_app_starts_without_exception` | clean startup (no import/signature/typo failures) |
| `test_list_renders_every_incident` | the unified list renders both domains |
| `test_open_incident_shows_workspace_and_url` | selecting an incident opens the right workspace and writes `?inc=` |
| `test_all_incidents_returns_to_list_and_clears_url` | back navigation works and drops the deep link (regression: it used to reopen) |
| `test_filters_survive_opening_and_closing_an_incident` | filter state survives a trip into an incident (regression: it used to reset) |
| `test_previous_and_next_move_between_incidents` | prev/next walk the queue and back again |
| `test_deep_link_opens_the_right_incident_and_only_once` | direct URL opens the right incident; closing it is not undone by the parameter |

### `tests/test_lifecycle.py` — recovery integrity, against a throwaway copy of the database

| Test | Asserts |
|---|---|
| `test_closure_is_blocked_without_a_verification_record` | no record → not closable, with a stated reason |
| `test_fix_applied_is_not_a_closure` | Mitigated verdict does not close |
| `test_inconclusive_is_not_a_pass` | undecidable checks are Inconclusive and block closure |
| `test_verified_with_open_request_is_still_blocked` | policy: outstanding request blocks closure |
| `test_verified_and_clear_closes_once` | Verified + clear → closes; a second close is refused |
| `test_verdict_mapping_is_explicit` | Investigating / Verified / Mitigated / Recovery failed mapping |
| `test_execution_is_recorded_once_and_reused_as_the_action_of_record` | one execution per incident; re-verification reuses it |

## Other suites

| File | Asserts |
|---|---|
| `tests/test_gate.py` | the closure gate end to end for every verdict, including Recovery failed and the open-request block |
| `tests/test_collab.py` | request → acknowledged → done → reopened, actor and timestamp recorded on each transition, overdue derivation, reopen clears `done_at` |
| `tests/test_analytics.py` | measured MTTR (median/p90), stage medians from the timeline, OLA delta sign, verdict counts, handoff delay with n=0; a verdict-less incident is excluded, never counted as zero |
| `tests/test_seed.py` | `meta.seed_version` equals `VERSION`, and `_needs_seed()` is false for a current database |
| `tests/test_workspace_scroll.py` | the workspace has one scroll surface (no clamped panel height), the primary action opens the guided step it names, and the DataOps view uses the same anchored wizard |
| `tests/test_clock.py` | the demo clock: `align(path=…)` re-anchors a stale database, is memoised per path until forced, and a new session copy is re-aligned while the base is left alone (regression: a tab opened hours after start showed every incident as 12h waiting · BREACHED) |
| `tests/test_navigation.py` (search/filter) | board search, filter reset and the empty-state message |
| `tests/test_learn.py` | a saved learn record is written to disk and read back; it is retrievable from the incident and from the list; similarity matches the failure signature (not the service alone); the seed carries a non-confirmed decision and a reused record |
| `tests/test_graph.py` | every incident is a node; the node/edge vocabulary is closed; every edge carries source, confidence and observed/inferred; neighbours group by edge type and keep direction; observed and inferred are both present on INC-8841 and the DB-saturation link is `inferred ≤ 0.35`; `path()` finds the cross-domain route and `traverse()` stops at depth; dropping the graph tables and calling `ensure()` rebuilds it without losing incidents or comments; the panel renders on the incident screen |
| `tests/test_stages.py` | the eight stages are defined once and the four phases cover them exactly once, in order |
| `tests/test_learning_metrics.py` | cause-confirmation accuracy counts confirmed vs overridden with its n; an empty sample is `None` (a dash), never zero; MTTR is split only by records saved *before* the incident was raised |
| `tests/test_stages.py` | one stage list (`journey.LIFECYCLE` = `viz.RESOLUTION_FLOW` = `analytics.STAGES`), the audit/funnel/OLA vocabulary only names those stages, the thread spine and every `next_action` use them |
| `tests/test_honesty.py` | the competing DB signal is ranked 4th of 4 with low/30% confidence; staleness is one computed number rendered in the thread, the hypotheses and the metric card |

## Not covered yet (honest list)

- Browser Back/Forward across a *history* of incidents: the URL is authoritative for refresh and direct
  links, but in-app navigation does not push browser history entries.
- Concurrency: two users acting on the same incident.
- Real connectors (everything is simulated), so delivery/acknowledgement is untestable today.
- Visual regression; screenshots are taken manually per milestone.
