# PROTOTYPE NOTES — Resolution Intelligence POC

Build v42 · sample data · simulated actions. This is a proof of concept, **not** production.

## What persists, and for how long

Operational state lives in **SQLite** (`data/ops.db`) plus a DuckDB KPI history file. This is
durable **within a running container**:

| State | Stored in | Survives rerun / navigation / new browser session | Survives app restart / redeploy |
|---|---|---|---|
| Authoritative verdict, action, verification checks, actor, closure time | `resolution_state` | ✅ | ❌ (container filesystem is ephemeral) |
| Incident stage, confirmed cause | `incidents` / `dop_incidents` | ✅ | ❌ |
| Activity history (timeline, comments, delegations, notifications) | `timeline`, `comments`, `delegations`, `notifications` | ✅ | ❌ |
| UI selections (open incident, lens, filters, demo persona) | Streamlit session state | ✅ (per session) | ❌ |

**Verified:** a verdict recorded via the UI is read back by the board and every role view after a
fresh session (see the release checklist tests). **Limitation:** on Streamlit Community Cloud the
app filesystem is ephemeral, so a reboot/redeploy **wipes and re-seeds** the database. Durable,
multi-user persistence requires a shared backend — which is deliberately out of scope here.

## Recovery-state rules (enforced)

`Investigating → Mitigated → Verified → Recovery failed`, with `Closed` only after **Verified**.
Applying a remediation **never** marks an incident Verified or Closed. Every view (workspace,
role lenses, board cards, verification panel) reads the **same authoritative verdict** via
`journey.current_verdict` / `journey.display_verdict`, and success wording is produced by one
shared helper (`journey.render_recovery_by_verdict`) — so no view can claim "restored" unless the
verdict is Verified.

## Cross-domain thread

Relationships are **structured records** in `thread_edges` (source, target, relationship type,
observed/inferred kind, evidence source, timestamp, rule-based confidence). UI code no longer
builds edges by hand; `journey.thread_edges_for()` resolves a thread via the correlation model.
Inferred relationships are labelled as hypotheses, not proven facts.

## Simulated operations

Remediation, notifications and status updates are **simulated and local**. The rail actions write
local demo comments — they do not contact any external system or person, and say so.

## Collaboration & resolution-acceleration metrics

Collaboration is presented as the resolution accelerator: a banner in every incident workspace
and a top-level **Collaboration** destination show who is engaged, handoffs, and coordination time
(these are derived from real comment/delegation records). The **MTTR / resolution-acceleration**
figures (baseline ➜ with-platform) are **illustrative simulated demo values**, clearly captioned,
and must be measured against a real baseline in a pilot before being treated as results.

## Known limitations / production gaps

- No live connectors (ServiceNow, Jira, observability); sample data only.
- No shared backend / multi-user state; verdict persistence is per-container.
- No RBAC or tenancy.
- OLA timers use incident-creation / first-delegation proxies, not true stage-entry timestamps.
- Analytics is an honest placeholder (no meaningful metrics yet).
- Global search covers incidents, services, datasets and pipelines (not full-text of thread evidence).
