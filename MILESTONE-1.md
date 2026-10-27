# Milestone 1 — P0 report

Scope: the P0 list (build verification, navigation flow, lifecycle and recovery integrity) plus
end-to-end tests. No redesign, no new features.

Commit: see `git log -1` / the footer label `build vNN · <sha> · <time>`.

## 1. Latest build verification

| Change | File | Why |
|---|---|---|
| Build identity from git (number, sha, commit time, dirty flag) shown in the footer and sidebar | `build.py`, `app.py`, `shell.py` | "Is the deployed build the commit I pushed?" was previously answerable only by trusting a hand-edited string (`build v77`). Now the UI states the commit; a mismatch is visible at a glance. |
| Deployment smoke test: imports, headless boot, open incident, back to list, URL cleared, build matches `--expect <sha>` | `scripts/smoke.py` | A clean, repeatable "is this deployment healthy?" gate. |
| Removed 191 lines of dead board code (`render_board`, `_needs_attention_cards`, `_thread_cards`, `_recent_activity`) and `journey.toggle_incident` | `app.py`, `journey.py` | Two implementations of the same page existed; the unused one could be edited by mistake and silently drift from the one that renders. |
| Test suite (14 tests) with `pytest` + Streamlit's `AppTest` | `tests/` | P0 requires end-to-end workflow tests, not component tests. |

Evidence: `python3 scripts/smoke.py` → `SMOKE PASSED`; `python3 -m pytest tests -q` → `14 passed`.

## 2. Incident navigation flow

| Change | File | Why |
|---|---|---|
| Deep link is consumed once per session; closing the workspace also removes `?inc=` | `app.py` | Closing used to be undone by the next rerun, so "← All incidents" appeared broken. |
| Board filters mirrored into plain session keys and restored on return | `app.py`, `shell.py` | Streamlit drops widget state for widgets that are not rendered, so filters/search reset whenever you opened an incident. Now they survive, including a persona switch. |
| List rows are whole-row buttons (replacing the dataframe) | `viz.py`, `app.py` | The dataframe only opened on its checkbox; clicking a row did nothing. A click anywhere now opens the incident. |
| Prev/next keep the URL in sync; `?inc=` is the single source of truth on load | `app.py` | Refresh and pasted links resolve to the same incident; walking the queue never leaves a stale parameter. |

Known limitation: browser Back/Forward still traverse document history, not an app-level history of
incidents (in-app Back, refresh and direct URLs are correct).

## 3. Lifecycle and recovery integrity

| Change | File | Why |
|---|---|---|
| `closure_state()` — one authority for closure, returning explicit reasons | `journey.py` | Closure was implicit (a record was written on Verified, but nothing gated or explained it). |
| `close_incident()` — closes only through the gate; sets status, closed_at, timeline event, thread entry; refuses a second close | `journey.py` | Closure is now an auditable action with a single code path. |
| Closure gate UI at the end of the workspace: eligible → **Close incident**; otherwise **Closure blocked · N requirement(s) open** with each failing check listed | `viz.py`, `app.py` | The user sees why closure is refused instead of a silent no-op. |
| Duplicate execution blocked: the applied action is shown with its verdict, the Apply button is disabled, and **Re-run independent verification** replaces it | `personas.py`, `dataops_views.py` | Re-applying a remediation mutated the same incident twice and could overwrite the verdict; re-verification is the safe operation. |
| `Inconclusive` verdict state added (applied but checks undecidable) and wired through verdict colours, filters and closure rules | `journey.py`, `command_center.py`, `app.py` | Previously an undecidable check fell into "Recovery failed", which is a false statement. |

Evidence: `tests/test_lifecycle.py` (7 tests) — blocked without a record, Mitigated does not close,
Inconclusive does not close, open request blocks closure, Verified + clear closes once, verdict mapping,
single execution of record.

## Remaining defects / limitations after Milestone 1

1. Browser history: no app-level Back/Forward stack (refresh and direct URLs are fine).
2. Closure policy is enforced in the app layer only; with no auth, the API-equivalent path (session
   state) could be manipulated. Server-side enforcement is Milestone 3.
3. Persistence is a local SQLite file; a restart keeps data but there is no shared/durable store.
4. Everything operational is simulated and labelled as such — no connector delivery, no acknowledgement.
5. Analytics still mixes live and illustrative numbers (labelled, but Milestone 2 must compute stage
   durations from lifecycle timestamps).
6. No concurrency control: two users applying to the same incident race.

## Verification performed

- `python3 -m pytest tests -q` → 14 passed.
- `python3 scripts/smoke.py` → SMOKE PASSED (imports, boot, open, URL, back).
- Manual UI pass: list, open, back, prev/next, filters preserved, collaborate, closure gate (blocked
  and eligible paths), duplicate-execution block.
- Screenshots: `screenshots/v78-gate-open.png` (blocked reasons), `screenshots/v77-list3.png` (list).
