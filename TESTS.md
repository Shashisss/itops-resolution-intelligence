# Tests — how we know it works

Two layers, both runnable without a browser.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests -q          # 71 tests, ~20s
python3 scripts/smoke.py            # deployment smoke test, ~5s
```

`scripts/smoke.py` is the check to run before claiming a deployment: imports every module, boots the
app headless through Streamlit's own harness, opens an incident, follows the URL, goes back to the
list and asserts the URL was cleared. It exits non-zero on the first failure.

## What is covered

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
