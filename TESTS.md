# Tests — how we know it works

Two layers, both runnable without a browser.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests -q          # 14 tests, ~6s
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

## Not covered yet (honest list)

- Browser Back/Forward across a *history* of incidents: the URL is authoritative for refresh and direct
  links, but in-app navigation does not push browser history entries.
- Concurrency: two users acting on the same incident.
- Real connectors (everything is simulated), so delivery/acknowledgement is untestable today.
- Visual regression; screenshots are taken manually per milestone.
