# PROTOTYPE NOTES — Resolution Intelligence POC

Build v93 · sample data · simulated actions. This is a proof of concept, **not** production.

## Persistence boundary — what survives what

The running demo is deliberately disposable. At start-up the app seeds `data/ops.db`, then
**every browser session gets its own copy** of it (`store.db()` writes `data/session_<id>.db`).
All actions — verdicts, closures, comments, requests, notifications — are written to that
session copy.

| What | Where | Rerun / navigate | Refresh the page | Restart / redeploy |
|---|---|---|---|---|
| Verdict, action, checks, actor, closure time | `resolution_state` | survives | **reset to seed** | reset to seed |
| Incident stage / confirmed cause | `incidents`, `dop_incidents` | survives | reset | reset |
| Thread history | `timeline`, `comments`, `delegations`, `notifications` | survives | reset | reset |
| UI selections | Streamlit session state | survives | reset | reset |

- **Nothing is persisted outside the container.** There is no shared database, no user account,
  and no server-side save. Two browsers are two independent copies.
- **Refresh resets the demo.** That is the point: the same script can be run again without a
  cleanup step. `RI_DEMO_MODE=0` switches the app (and the tests) to the single base database
  `data/ops.db`, which still disappears when the container is rebuilt.
- Tests and tools that must not depend on a browser session use `RI_DB` / `RI_DEMO_MODE=0`
  against a throwaway copy of the base database.

## The demo clock only shifts sample data

`clock.align()` slides every stored timestamp forward so the newest sample event sits a few
minutes behind wall-clock time. It moves **sample-data timestamps only** — no real event, system
or person is observed, and no external clock is read or written. Relative distances inside the
scenario are preserved; the incident keeps its shape while "3h 12m left" stays plausible a day
later. A real deployment would take stage-entry times from the connected systems, not shift them.

It runs twice, because the database exists twice: once per process against the seeded base, and
once per browser session against that session's copy (`store.db()` re-aligns the copy as it is
made). Aligning only the process was not enough — a page opened hours into a long-running deploy
cloned a base aligned at startup, so every incident read "12h waiting · BREACHED".

## All communication is simulated and local

Every channel selector (Teams, Slack, Email, App) is a **label recorded on the local request**.
No connector is configured and nothing is sent: the Collaborate form, "Ack", "Done", "Chase",
notifications, status updates and escalations only write rows to this session's SQLite copy and
say "(simulated)". A request is **logged, not delivered**. The UI never claims that a message
reached a person or an external system.

## Recovery-state rules (enforced)

`Investigating → Mitigated → Verified → Recovery failed`, with `Closed` only after **Verified**.
Applying a remediation **never** marks an incident Verified or Closed. Every view (workspace,
role lenses, board cards, verification panel) reads the **same authoritative verdict** via
`journey.current_verdict` / `journey.display_verdict`, and success wording is produced by one
shared helper (`journey.render_recovery_by_verdict`) — so no view can claim "restored" unless the
verdict is Verified.

## Collaboration semantics

A request moves through `assigned → accepted → done`, and `reopened` is a **distinct state**, not
a quiet return to `assigned`. Every transition stores the actor and the time (`actor`,
`changed_at`), and the full trail is appended to `delegation_events`. The Open requests list shows
`by <actor> · <when>`; a request open longer than 30 minutes is marked OVERDUE. `done_at` is
written only on completion and is never backfilled — an earlier request has no measured delay
rather than an invented one.

## Analytics — measured, with sample sizes

The Analytics page is computed from stored lifecycle timestamps (`analytics.py`, pure SQLite
functions): MTTR median/p90 from `resolution_state.closed_at − incidents.created_at` for verified
records only, stage medians from consecutive timeline/comment/handoff anchors, OLA vs actual from
`stage_olas`, verdict counts, handoff delay from `done_at − ts`, and SLA/breach load per priority.
Every panel states its provenance and `n=`; a panel with n < 5 is labelled "indicative, not
significant"; a number the data cannot support is a dash, never an estimate. Illustrative scenario
figures appear only where a panel has no data at all, clearly labelled. **No ROI or benefit claim
is made.**

## Cross-domain thread

Relationships are **structured records** in `thread_edges` (source, target, relationship type,
observed/inferred kind, evidence source, timestamp, rule-based confidence). UI code no longer
builds edges by hand; `journey.thread_edges_for()` resolves a thread via the correlation model.
Inferred relationships are labelled as hypotheses, not proven facts.

## Migration path to production

1. **Database** — replace SQLite with Postgres. Keep the same tables as the migration baseline,
   add real foreign keys and a deterministic seed/version procedure. Every per-session copy becomes
   a real tenant-scoped database, not a file copy.
2. **Identity & authorisation** — real sign-in (OIDC/SAML), RBAC per domain, and an immutable
   audit table for every state change. `actor` stops being a demo persona string and becomes the
   authenticated subject; tenancy is enforced at the query layer.
3. **Connectors** — ServiceNow/Jira for tickets and changes, observability/metrics for signals,
   data-catalogue/lineage for DataOps, and Slack/Teams only if outbound delivery is configured and
   consented to. Delivery must be idempotent, retried and audited; until then the UI keeps saying
   "logged locally, not delivered".
4. **Clocks & SLAs** — stage-entry timestamps come from the connectors, not from shifted sample
   data; OLA/SLA targets become configuration with time zones and business calendars.
5. **Analytics** — run the same measurements on durable data, publish sample sizes and confidence
   intervals, and establish a real baseline before any benefit claim.

## Known limitations / production gaps

- No live connectors (ServiceNow, Jira, observability, Teams/Slack); sample data only.
- No shared backend, multi-user state, RBAC or tenancy; every refresh starts from the seed.
- Communication and outbound notifications are simulated and local.
- OLA timers use recorded anchors/proxies, not guaranteed true stage-entry times.
- Analytics is honest but thin: small samples are labelled indicative, not significant.
- Global search covers incidents, services, datasets and pipelines (not full-text of thread evidence).
