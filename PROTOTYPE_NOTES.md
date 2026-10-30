# PROTOTYPE NOTES — Resolution Intelligence POC

Build v110 · sample data · simulated actions. This is a proof of concept, **not** production.

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
| **Learn record** (root cause, steps, outcome, evidence) | `data/learn.json` | survives | **survives** | reset |
| UI selections | Streamlit session state | survives | reset | reset |

- **Nothing is persisted outside the container.** There is no shared database, no user account,
  and no server-side save. Two browsers are two independent copies.
- **Refresh resets the demo.** That is the point: the same script can be run again without a
  cleanup step. `RI_DEMO_MODE=0` switches the app (and the tests) to the single base database
  `data/ops.db`, which still disappears when the container is rebuilt.
- Tests and tools that must not depend on a browser session use `RI_DB` / `RI_DEMO_MODE=0`
  against a throwaway copy of the base database.
- **Learning is the one exception, on purpose.** A learn record is written to
  `data/learn.json` (override with `RI_LEARN_PATH`), not to the session copy, because a page
  reload replaces that copy and the whole point of the Learn stage is a durable record. The
  document is seeded once from sample records; edits replace a record by incident id. It is a
  file in the container, so it survives reloads and sessions but not a rebuild or redeploy —
  a real deployment would put it behind the same store as the incident.

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

## v110 — the Requests tab works (milestone 1)

The rebuild had reduced the incident to two actions (`?action=chase`, `?action=confirm`). The
Requests tab is now a working list again, without touching the signed-off geometry:

- **Each request carries its actions** — Chase, Acknowledge, Mark done, and Send for an ask that was
  recorded but never handed over (NOT SENT → SENT). Every one is an `?action=<verb>&target=<id>`
  link that mutates the record through `collab`, records who and when, and re-renders on the same
  tab with the new badge (`OVERDUE`, `NOT SENT`, `SENT`, `ACKNOWLEDGED`, `DONE`).
- **Create ask** is an inline form in the pane (owner, action, deadline, what travels with it). It
  is created NOT SENT and the ask carries `· expected in <n> min`, which is the same deadline
  `story.deadline_minutes()` reads — one definition.
- **Pagination in place** — "Show all" expands inside the pane (no modal), eight to a page,
  `1–8 of 13` with prev/next; `?page=` and `?full=` live in the URL and every action href carries
  them, so an action lands back on the page it was taken from. The pane stays 164px: eight 17px rows
  plus the pager, or four preview cards, both measured in the CDP audit.
- **The tab header is derived**, not a literal: `Requests · N OVERDUE` counts the same rows the list
  badges, so resolving the last overdue turns it into `none overdue`.
- **Why the links no longer reload the page:** a full navigation starts a new Streamlit session and
  the per-session database copy would lose every earlier mutation. The component rewrites the
  parent's query string and lets Streamlit's own `popstate` handler rerun the app, so a sequence of
  actions accumulates in one session. (The iframe is sandboxed without `allow-forms`, so the ask
  form sends its fields the same way instead of relying on a native submit.)

Out of scope for this milestone: RCA, collaboration, act/verify, close, learn and the agent panel.

## v109 — the incident screen is one HTML document

The Streamlit container layout could not be made clean: bands with their own heights inside a fixed
wrapper produced overlaps that padding could not fix. The incident screen is now generated as a
single document by `incident_html.build()` and embedded with
`st.components.v1.html(html, height=704, scrolling=False)`.

- **Built from the record:** header (breadcrumb, title, pills, queue, clock), four tiles
  (Waiting on · Error rate · Data freshness · Checkout), the dependency graph, "what this means",
  the single action, six tabs and their panes. No literal numbers — every value comes from `story`,
  `journey`, `collab`, `learn` or the tables they read.
- **No Streamlit widgets inside** the incident area: nothing to collide on, no containers to fight.
  Tabs and "Show all" switch client-side; the full view is an overlay in the same document.
- **Actions** are anchors carrying `?inc=…&action=…` (chase / confirm / close / back), read once by
  `app.py` and cleared. Apply and Verify are inert by design and say so.
- **Layout:** `html,body{overflow:hidden}`, a flex column that fills 100% of the component, one
  fixed 172px pane band that clips (with the overlay for the long view). No `position:absolute`
  anywhere except inside the graph SVG.
- **Deleted:** the Streamlit incident renderers (`_core_strip`, `_collab_bar`, `_render_incident_detail`,
  `_extra_sections`, `_agent_panel`, `_tab_body`, `_act_tab`, `_accel_strip`) are gone, not left behind.

Tests that asserted the old Streamlit surfaces were retargeted onto `incident_html.build()` — the
document is now the contract.

## v107e — fits 1280×768, not just 1280×800

The page was measured at 1280×800 and shipped; at 1280×768 the same content needed ~800px, so the
page scrolled and the tiles looked like they overlapped the header. Fixed by removing the *cause*
(the tab labels wrapping to two lines at that width): tab columns now take a width proportional to
their label, the label font is 9.5px below 1320px, and the graph/body caps came down (SVG 186 → 170,
body 152 → 144).

Measured after the fix, both domains: 1366×768 → 768/768 and 1280×768 → 768/768, `scrollHeight ==
clientHeight`, bounding boxes of header / tiles / hero / tabs / body do not intersect at either size.

## v107d — overlap and the DataOps reading

- **Overlap:** the tiles had a fixed 70px height, so their content spilled 4px into the hero card at
  1280×800. They now size to their content (`height:auto`, min 64px, overflow hidden) with 10px of
  air below the row; the tab body cap moved 164 → 152 to keep the 768px page budget. Verified by
  measuring the bounding boxes of tiles, hero, tabs and body at 1366×768 and 1280×800 — no
  intersections, `scrollHeight == clientHeight` on both.
- **A DataOps incident read like an IT one.** On DOP-1001 the first tile said "Error rate 1 vs 0
  threshold" for a failed-run count; it now takes the record's own label ("Failed runs"). The graph's
  service node showed a dataset id — it now shows the pipeline (`payments_bronze_ingest`). With no
  inferred link on the thread, "What this means" no longer prints "Confidence —"; it says observed
  links only and claims no confidence.

## v107c — the duplicate-key crash on "Show all"

**Bug:** clicking "Show all · Evidence & RCA" raised `StreamlitDuplicateElementKey`. The overlay
rendered `_tab_body(...)` a second time beside the inline panel, so every widget inside it (the agent
panel's buttons, the connections panel, the learn form) existed twice with the same key.

**Fix:** the full view is rendered *instead of* the clipped body, not beside it. One section body per
render pass, keyed `fullbody_<ref>` when expanded and `tabbody_<ref>` when clipped, so the two forms
cannot coexist. "Close full view" clears the flag and returns to the clipped body with the same tab
still selected. The dialog is gone — an in-place full view needs no second render, which removes the
whole class of collision rather than papering over one instance.

`tests/test_viewport.py::test_every_full_view_opens_without_a_duplicate_key` opens and closes the
full view for Timeline, Requests, Evidence & RCA, Connections & audit and Learn, asserting no
exception, unique widget keys within the pass, and that the tab survives the round trip.

`st.button(width="stretch")` in `shell.py` is supported on the deployed Streamlit (1.66.1 — `width`
is in the signature); it appeared in the traceback as a context line, not as a cause.

## v107b — the graph hero, the four tiles, the underline tabs

- **Graph hero** replaces the last of the strip/chain. For INC-8841 it draws: CHANGE `core_ledger v4`
  --(dashed, inferred 0.72)--> JOB `payments_bronze_ingest` --(writes 0.85)--> DATASET
  `payments_gold` (stale 60m) --(feeds 0.95)--> SERVICE Payment API --(impacts 0.90)--> KPI
  `checkout 90%`, with the linked INCIDENT `DOP-1001` --(stale 0.85)--> the dataset. The held chip
  says "now · held here" so the wait is not repeated. Beneath: the caption "The break is upstream —
  the service is serving what it was given", an observed/inferred legend and the connections count.
- **Tiles** are exactly the approved four, in order: Waiting on · Error rate · Data freshness ·
  Checkout. Time-left lives in the header; handoffs in the graph and the Connections tab.
- **Tabs** are an underline strip (no pills), same six labels and state words; Act & verify remains
  the only uncapped tab.

Measured: 768/768 at 1366×768 and 800/800 at 1280×800 — no page scroll, on Cloud as well.

## Concept A — the one-viewport incident page (v108)

Approved design, implemented against `files/mockup-proposal-incident-page.png`.

- **Header**: breadcrumb, title, P2 + stage pills, queue position, one clock. Nothing else — the
  prev/next arrows were removed with the old strip.
- **Four tiles**: Waiting on (holder, duration, overdue) · Error rate (value + threshold line) ·
  Data freshness (value + SLA) · Checkout (value + baseline) — the mockup's order.
- **Hero**: the dependency graph on the left (change → job → dataset → service → KPI, plus the linked
  incident; observed edges solid, the inferred one dashed with 0.72; caption "the break is upstream"
  with the connection count), and on the right "What this means" (one sentence + confidence/basis),
  the single next action with one button, and who is on it.
- **Six tabs**: Timeline · Requests · Evidence & RCA · Connections & audit · Act & verify · Learn,
  each header carrying its state in words; content capped at 164px with "show all" in a dialog.
  Act & verify is uncapped — closing stays in-flow.

Measured at 1366×768 and 1280×800: `scrollHeight == clientHeight` (768/768, 800/800) — no page scroll.

Assumptions taken rather than inventing features: the graph's holder chip reads "now · held here"
(the wait is stated once, in the Waiting on tile); confidence is the stored signal's weight
(inferred/medium = 72%, not the mockup's illustrative 85%); the error-rate tile draws a threshold
line, not a trend, because the record holds one value per metric and no history.

## One viewport (v107a)

The incident page is one screen: a header row, four tiles, six tabs. No scrolling at 1366×768 or
1280×800 (measured in the browser: 768/768 and 800/800 — the page never overflows).

**Header** — title, P2 + stage pills, queue position, the single clock. Nothing else.
**Tiles** (92–100px) — error rate against its threshold, data freshness against its SLA, the share of
the SLA already used, and the handoff route with the holder and their wait. One number and one
qualifying line each; the wait, the domains and the SLA live here and nowhere else.
**Tabs** — Timeline · Requests · Evidence & RCA · Connections & audit · Act & verify · Learn. Each
header carries its state in words (`Requests · 2 open · 1 OVERDUE`, `Learn · draft, not saved`), so a
collapsed tab never hides a critical fact. Content is capped at 224px; "Show all" opens a full-height
dialog. Only **Act & verify** is uncapped — it is bounded by construction, one stage at a time, and it
holds Confirm cause, Apply remediation, Run verification and Close (gap-gated), so an incident can be
closed without opening any overlay.

Deep links: `?tab=Connections & audit`, `?step=Close` (lands in Act & verify at Close), `?expand=agents`
(maps to Evidence & RCA).

v107b replaces the leftover strip/chain space with the dependency-graph hero, inside the same cap.

## Progressive disclosure (v106)

The incident screen is an accordion. On load only the **current stage's content** is open — and it
is rendered first, so it is on screen without scrolling past the stages that precede it. Every other
stage, plus the agent panel, Connections, Evidence carried over, Activity & audit and Record/sources,
is one click away, and opening one closes the others (a single `open_<ref>` key per incident, so the
page height stays predictable).

A collapsed header is never a blank line. Each carries: the stage name, its state, its clock against
the stage OLA, and the single fact that matters most — and any critical state is in the header
itself, in words: `Close · BLOCKED`, `Verify · UNVERIFIED`, `Act · OVERDUE`.

Deep links: `?step=Correlate` opens a stage, `?expand=connections|evidence|activity|record|agents`
opens a folded section, applied once so the reader can then open something else.

The Incidents list answers the queue questions in the row itself: who holds it and for how long, the
SLA left, cross-domain or single, and the next action. Selecting a row opens a right-hand summary
drawer (waiting, SLA, domains/handoffs, blocker, next actor) with one button — **Open incident**.

Measured at 1366×768: 1187px total with every section collapsed.

## One clock per render (v105)

Every relative time is "now minus a stored timestamp". Computed per call, two of those inside one
render can straddle a minute boundary and print `60m` in the thread beside `61m` in the agent panel
for the same fact. `runclock.begin()` fixes one `now` at the top of each script run; `story`,
`journey.freshness`, `collab.age_minutes`, `dataops_engine._lag_min` and the OLA elapsed time all
read from it. One definition — now − `dop_freshness.last_updated` — one number, everywhere.

Outside a run (tests, scripts) `runclock.now()` is the real clock, so the functions stay pure.
`tests/test_story.py::test_freshness_is_one_number_across_the_page` renders the incident and asserts
every freshness figure on the page is the same integer.

## One statement per fact (v103)

The incident screen states each of its three headline facts in exactly one place — the hero strip:
who holds the work and for how long, the SLA clock left, and how far it has crossed. Everything
below the phase stepper is reserved for facts the hero does not carry.

Removed in v103: the second Owner/SLA/OLA/Stage card row under the stepper (both domains), the
Severity/Owner/SLA/OLA card row inside Triage, the dark status bar that repeated id/owner/SLA/verdict,
the third verdict badge, the SLA in the pinned bar and the sidebar rail, and the "asked 53m ago" that
restated the hero's wait on every request card.

What replaced the duplicate block: one small line — blocker · service (or dataset) · internal OLA —
which is the only one of those facts the hero does not show. Where there was nothing unique to say,
there is whitespace. `tests/test_story.py::test_wait_sla_and_owner_are_stated_once` renders the page
and counts the occurrences: the wait and the SLA clock must each appear once.

## Who's on it — the agent panel (v102)

`agents.json` (committed at the repo root) is a **static** per-incident definition: the routing
decision, the specialist that acted, the draft ask and the autonomy rung. There is no agent runtime,
no model call and no orchestration engine; the Agents page says so in its header.

The numbers are not in the file. `agents.facts()` computes every one of them from the record at
render time — waiting clock and holder (`story.waiting`), SLA (`story.sla`), domains and handoffs
(`story.cross`), freshness (`journey.freshness`), the breaching metric (`metrics`), the upstream link
(`journey.correlation_for`), the signals reviewed (`thread_edges`), the leads ranked and set aside
(`engine.causes` / `dataops_engine.causes`), and the signal weight. That is why the panel cannot
contradict the screen beside it: change the record and the panel changes with it (test-asserted).

Signal weight has one definition: `agents.SIGNAL_SCORE` maps the recorded basis and confidence to a
number — observed 0.95/0.90/0.85, inferred 0.85/0.72/0.55. On INC-8841 the ledger link is recorded
inferred/medium, so the panel reads **0.72 inferred**.

Craft rules specific to this panel:

- a visible `SIMULATED` chip in the heading, never a tooltip;
- the handoff is labelled **NOT SENT**, and Approve / Edit / Reject are **disabled**, with a caption
  saying they are inert — a control that does nothing must not look active;
- an incident with no definition gets a neutral empty state that changes nothing above it;
- one highlight only: the rung the incident is actually on.

Four incidents are defined (INC-8841, INC-8850, INC-8802, DOP-1001). DOP-1002 is deliberately
undefined so the empty state is demonstrable. `tests/test_agents.py` renders each one and compares
the panel's numbers to the record.

## Ask — grounded questions (v101)

The Ask box (Incidents and Analytics) parses a question into a four-intent schema and executes it
against the same functions the Analytics page uses. No model is called; no answer is written from
prose.

| Intent | Trigger | Computation |
|---|---|---|
| `count` | "how many … incidents/reported/failed/raised" | `analytics.created_between(start, end, status)` — created_at window + status bucket; `failed` = verdict `Recovery failed` |
| `summary` | an incident id + "summarise / what happened / walk me through" | `timeline` events in order + `story.hero/chain/acceleration` — raise, signals, holder, what unblocked it, how it ended |
| `held_longest` | "which domain held us longest / slowest" | `analytics.held_by_domain(start, end)` — delegation clocks grouped by the recipient's domain |
| `median_resolution` | "median / average / typical … resolution / MTTR / time to close" | `analytics.mttr_between(start, end)` — the MTTR filter, windowed by `closed_at` |

Every answer card carries: the interpretation with the exact dates, the number (or the narrative)
with its n, **Show the query** (the statement actually executed, with its parameters), and the
tables/definitions it rests on. An unsupported question returns the same card shape with an em dash,
the reason, and three questions it can answer — it never shows a number.

Windows are rolling and stated in full on the card ("created between 28 Oct 00:00 and 28 Oct 23:59"),
so "last month" cannot quietly mean two different things. A window with no verified closure answers
with a dash plus when the most recent closure was, and a chip to widen the window.

Twenty questions (thirteen supported, seven unsupported) plus six behaviour tests live in
`tests/test_ask.py`; each supported number is checked against an independent SQL count in the test.

## The story layer (v100) — one definition per claim

Three ideas have to be unmistakable on every incident screen: **cross-domain**, **collaboration**
and **accelerated resolution**. Every number that states one of them is computed once, in `story.py`,
from stored timestamps and row counts — and the UI prints it, it does not recompute it.

| Claim | Definition | Where it is computed |
|---|---|---|
| `Waiting 53m · Data Platform` | now − `delegations.ts` of the **oldest open request**; the name is its `to_` | `story.waiting()` |
| `7h 2m left` | `SLA_HOURS[priority]` − (now − `incidents.created_at`); `SLA_HOURS` is defined once and re-exported by personas/csm/developer | `story.sla()` |
| `3 domains · 2 handoffs` | distinct `domain` labels on the handoff chain; `COUNT(delegations)` | `story.cross()` |
| Handoff chain | origin service/dataset → the current holder (oldest open request's `to_`) → the correlated incident; each hop prints its own clock | `story.chain()` |
| `Time to next action` | first recorded action (delegation or repair) − `incidents.created_at` | `story.acceleration()` |
| `Unblocked by evidence` | first alert/ticket/repair recorded **after** the request was raised − the request's `ts` | `story.acceleration()` |
| Learn inheritance | the signature's newest record: confirmed cause + the steps that worked | `story.inheritance()` |

If the record cannot support a number, `story` returns `None` and the UI prints an **em dash** with
the reason ("no action recorded yet"). No saving is ever estimated. A closed incident's clock stops
at `resolution_state.closed_at`, so a six-day-old closure reads `held 40m`, not `held 6d`.

**Craft tokens (v100).** One type scale (`--ri-fs-xs…xl`), one spacing grid (`--ri-sp-1…4`) and one
interaction accent (`--ri-accent`) live in `viz.CSS`; semantic state colours (red/amber/green) stay
for state only. Every state is designed: empty ("No open request — nobody is holding this"), stale
(the chain prints `60m stale · 15m SLA`), closed ("closed on the verified record"), and error (the
reload-failure banner). Focus rings are global (`:focus-visible`). The footer states build, commit
and that the data is sample data. Checked at 1366×768 (projector) and at 390px (phone).

## The graph store (v99)

The screen now reads a property graph, not the flat tables: `graph.py` holds `graph_nodes`
(id, type, business_key, properties, version, valid_from/valid_to) and `graph_edges` (from, to,
type, properties, source, confidence, basis, version, valid_from/valid_to). Node types are
Incident, Signal, Change, Service, KPI, Runbook, Learn, Team, Policy; edge types are caused_by,
observed_in, affects, resolved_by, evidenced_by, learned_from, depends_on.

- **One interface.** `GraphStore.neighbours()`, `path()` and `traverse()` are the only reads the UI
  does (`graph_views.connections_panel`). Swapping SQLite for Neo4j means reimplementing those
  three methods plus the upserts — the views do not change.
- **Provenance is on the edge, not the node.** `basis` is observed or inferred, and `confidence` is
  0..1 with the `source` string the claim came from. A metric is an observed fact; the claim that
  it caused the incident is inferred — that is why the DB-saturation signal shows as
  `inferred · 0.30` next to `observed · 0.90` telemetry.
- **Projection, not a second fixture.** `graph.project()` reads the relational tables and upserts
  the graph; `graph.ensure()` runs it when the graph is missing, which is how a database built by
  an earlier release gains the graph without losing a row. `seed.py` projects after writing.
  `write_many(..., replace=True)` clears the previous projection first, so a claim the projection
  no longer makes (a runbook that is no longer recommended) cannot linger.
- **One definition of staleness still holds.** `data_age_min` and freshness signals take their value
  from `journey.freshness()` at projection, and the panel rewrites any stored number with
  `journey._stale_text()` at render, so the graph cannot disagree with the Investigation section.
- **Legacy labels are migrated once.** Free-text `thread_edges` labels map onto node ids through
  `LEGACY_ALIASES` (with a name fallback), keeping the original source, confidence and
  observed/inferred kind.

Limits: the graph is rebuilt from the relational tables on each session start, so an action taken
mid-session appears in the panel only after the next projection (Learn save triggers one); there is
no graph query planner, no multi-hop weighting, and `path()` is undirected by default because the
screen's question is "how are these connected", not "which direction did it flow".

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
