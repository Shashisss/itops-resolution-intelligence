# CONTEXT PACK — "Resolution Intelligence" (give this whole file to ChatGPT)

## 1. One-liner
A governed **IT Operations Resolution & Intelligence Platform** — connects IT Ops and DataOps systems of record,
reasons over one shared model, coordinates the next responsible person, acts under policy, and **verifies the
business outcome** before closing.

## 2. What it is / how it's built & hosted
- Prototype: **Python + Streamlit**, deployed on **Streamlit Community Cloud**, source on **GitHub**
  (repo: `github.com/Shashisss/itops-resolution-intelligence`).
- Deterministic reasoning: **graph traversal + rules** (not autonomous/learned RCA). AI is used to reason over
  governed evidence. All data is **sample data**; all remediation is **simulated**.
- Data stores: **SQLite** (operational state) + **DuckDB** (history/KPI). Front end styled with CSS.

## 3. Reference architecture (one page)
Three independent planes + cross-cutting controls:
- **DATA PLANE** — Sources (ServiceNow, Jira, CMDB, observability, cloud, DevOps, business) → Integration
  (APIs · CDC · events · streaming · batch · schema validation · retries/DLQ · dedup · reconciliation) →
  **Semantic / Governed Data Product layer** (domain model/ontology · data contracts · governed data products ·
  knowledge graph · catalog · search/vector · business semantic layer · **lineage: source → product → KPI**).
- **INTELLIGENCE PLANE** — Agent **Orchestrator** (context · reasoning · planning · tool selection · handoff ·
  memory · policy) + specialists (Incident, RCA/Diagnosis, Problem, Change, Risk/SLA, Knowledge, Business Impact,
  Prediction); grounded RAG; evaluation · grounding · model/agent lifecycle · threat controls.
- **OPERATIONAL CONTROL PLANE** — Policy · approval · workflow · collaboration · escalation · action
  orchestration · automation · verification · learning; least privilege · risk policy · rollback · action audit.
- **Cross-cutting**: security · identity/access · data governance · AI governance · lineage · data quality ·
  auditability · resilience/DR · platform observability · FinOps · privacy.
- Closed loop: **Action → technical health check → service & business KPI validation → evidence captured →
  knowledge/policy improvement**.
- Outcomes: ↓MTTR · ↓SLA breaches · ↓repeat incidents · ↓effort · ↓business impact · ↑resolution confidence ·
  business-aware CSM narrative · verified resolution · measurable ROI.

## 4. Production flow (SNOW + Jira as the starting point)
**Where events are born:** ServiceNow (incident raised/updated, change raised/approved, CMDB CI changes, SLA
clock) · Jira (defect logged, build/deploy, release) · observability/cloud (alerts, metrics, logs, CI/CD).

**Pipeline (every event):**
1. **Ingest** — SNOW & Jira via API + webhooks; alerts via event stream; history via CDC. (Read; write-back later.)
2. **Validate** — data-contract check → accept or **quarantine**; dedup + enrich; never silent drop.
3. **Normalize** — map SNOW "incident" and Jira "defect" into **one common model**.
4. **Relate** — link over the graph: incident → service → dependency; incident → recent change; defect → incident;
   person → owner.
5. **Detect & Reason** — correlate the event against the living model; rank likely causes with **evidence +
   confidence**; cause stays **suspected** until a human confirms.
6. **Coordinate** — decide **next owner + next action**; start the internal **OLA** clock.
7. **Act** — risk-classed: **approval** for production → execute (runbook/automation), fully logged.
8. **Verify** — re-check raw signals (metrics, freshness, quality, service health) → **Verified / Mitigated /
   Recovery failed**.
9. **Learn** — update knowledge, runbooks and rules.

**How does the system know?** It keeps a living model of services, dependencies, owners and recent changes,
built from SNOW + Jira + observability. A new event is matched to the model via three checks:
- **Relationship** — does this alert touch a CI/service with a recent change or open incident? → correlation.
- **Threshold** — is a metric / SLA / freshness value beyond its limit?
- **Pattern** — does it look like a past incident (similarity / ML)?
If any fires, the system creates or enriches the incident and pulls the full context automatically. (An event is
just a signal; it becomes an incident when correlated with the model.)

## 5. Two commitments: SLA vs OLA
- **SLA** = customer-facing commitment (shown as a countdown in the header).
- **OLA** = **internal** Operational Level Agreement — the owner-team target, shown **per resolution stage** and
  per handoff (targets come from a configurable `stage_olas` / `olas` table). The active stage shows live
  remaining / BREACHED.

## 6. Truthful recovery (verification governs closure)
States: **Investigating · Mitigated · Verified · Recovery failed**. Applying a fix **never** means closed:
- **Verified** → incident may close.
- **Mitigated** (partial) and **Recovery failed** → incident **stays open**.
- Verification is an **auditable record**: check · observed value · threshold · timestamp · verifying actor ·
  result — independent of the operator who applied the change.

## 7. Cross-domain resolution thread (the core object)
The product's differentiator: an **IT incident and a data failure resolve as ONE thread** — shared cause, one
owner, coordinated action, verified outcome. Example: `Schema mismatch → Pipeline failure → Stale payments data →
Payment API impact` (nodes labelled by domain). A canonical timeline merges events from both domains.

## 8. The app (what a user sees)
- **Three domains in one product:** **IT Ops**, **DataOps**, **Live Operations** (same navigation, data model,
  history and design language).
- **Top bar:** domain switcher with open counts, global incident search, notifications bell (unread + mark-read),
  demo persona selector.
- **Incident workspace (IT Ops → "Resolution thread"):** hero header (priority, status, incident id, SLA
  countdown, domain chips) → **lifecycle strip** (single progress model) → **resolution thread spine**
  (Detect · Correlate · Coordinate · Verify · Close, each with its OLA) → tabs: Overview · Investigation · Impact ·
  Collaboration · Verification · Timeline. Right rail: live event feed, team & ownership, quick actions, recent
  activity. KPI cards lead with business impact, status, next owner, next action.
- **DataOps** uses the same shell (pipelines, data quality, freshness, lineage, consumers).
- **Live Operations:** shared event feed (Live/Replay modes), incident queue with search/domain/priority filters,
  SLA countdown, collaboration thread with **@mentions → role notifications**, and **delegation**
  (assigned → accepted → done).
- **Personas (role lenses):** IT Ops — CSM, L1, L2/L3, Developer, Incident Manager; DataOps — Data Engineer,
  Data Owner, Platform Engineer, Data Consumer. "Guided journey" = a 5-step wizard (Detect → Diagnose → Decide →
  Act → Verify) with handshakes between stages.

## 9. Data model (tables)
services, edges (service graph), incidents, changes, metrics, tickets (Jira), kpis, service_data, pipelines,
dop_datasets, dop_lineage, pipeline_io, dop_runs, dop_dq, dop_freshness, dop_contracts, dop_consumers,
dop_incidents, timeline, correlations, live_events, comments, delegations, notifications, olas, stage_olas.

## 10. Honest limitations (state these)
- Deterministic, rule-based reasoning — **not** autonomous root-cause analysis; hypotheses are human-confirmed.
- **No live connectors**; sample data; no real logs/traces; remediation/recovery is **simulated**.
- SLA/KPI figures are scenario-specific estimates; real-time is simulated; true multi-user needs a shared backend.
- No RBAC/tenancy yet.

## 11. What I want feedback on
How to make this a best-in-class enterprise operations product: information architecture, the incident-first
workspace, the cross-domain resolution thread, truthful verification, visual system/accessibility, and the
path from prototype to production (connectors, real-time backend, tenancy/RBAC). Also: what is the strongest
differentiator vs Datadog / ServiceNow / PagerDuty / Monte Carlo, framed honestly.
