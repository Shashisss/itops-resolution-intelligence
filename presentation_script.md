# Resolution Intelligence — Demo Script (simple, ~10 min)

**App:** https://itops-resolution-intelligence-7h4kpseynvdeka77mqw5dk.streamlit.app/
**Repo:** https://github.com/Shashisss/itops-resolution-intelligence

---

## Before you start
- Open the app; let it load (~30s if asleep). Caption should read **build v24**.
- One scenario weaves through everything: **a source schema change → pipeline failure → stale data → a payment (business) incident.**
- **Navigation to know:**
  - Top: **Operations domain** → `IT Ops` · `DataOps` · `Live Operations`
  - Sidebar (in IT Ops / DataOps): **View** → `End-to-end journey` *(default)* or `By role`
  - **Persona** appears **only** under `By role` (roles only)

---

## 1. How it's built & hosted (say this first, ~40s)
> "It's a **Python / Streamlit** app deployed on **Streamlit Community Cloud** from a **GitHub repo** — you open a browser link, nothing to install.
>
> The reasoning is **deterministic** — graph traversal plus rules, not a black box. It runs on **sample data** with **simulated actions** — a credible proof of concept, not a production deployment."

*(If asked "real-time?": the stream is simulated and auto-refreshes; true multi-user real-time needs a backend.)*

## 2. Opening line (10s)
> "This is **Resolution Intelligence** — one governed platform across **IT Ops and DataOps**. Watch one incident travel the whole journey: **detect → understand → decide → act → verify** — across both domains."

---

## 3. The 90-second story — Live Operations
1. Domain → **Live Operations**.
2. Stream mode → **Replay** → **⏮ Reset** → **▶ Play** (or step with **⏭ Next**).
3. Narrate as cards appear:
   > "A source schema changed → the ingestion pipeline failed → payments data went stale → the payment service served stale data → a business incident opened."
4. Point at the **queue cards** (IT + DataOps together), the **SLA countdown** ticking, the **severity-coloured feed**.
   > *(Live mode = an always-moving random stream; Replay = the same story, repeatable for recording.)*

---

## 4. The deep journey — IT Ops
1. Domain → **IT Ops**, **View = End-to-end journey**. Incident **INC-8841**. The journey is a **5-step wizard** —
   **Detect → Diagnose → Decide → Act → Verify** (use **Next →** / **← Back**, or click a step). One progress bar highlights where you are.
2. **Detection** + **vertical timeline** (change → alerts → incident → ticket).
3. **RCA hypothesis cards** — the top card is the real cause:
   > "The tool ranks the true cause first — **upstream data is stale** — above the symptoms. Each hypothesis shows **confidence and evidence**; a suspected cause must be **human-confirmed**."
4. **Recommended action** card → **🟢 Coordination — autonomous under policy** + **next actor** chips.
   - Toggle **🤖 Auto-coordinate on open** (sidebar) → the delegation + notification appear automatically:
     > "The system **mobilised the right people** under policy — no email, no chase."
   - Scroll to **Section 7** → **🔴 Execution — human approval**: *"…but the production change still waits for me."*
5. **🔗 Cross-domain correlation** → click **View DOP-1001 in DataOps →**.

## 5. The deep journey — DataOps
1. Now in **DataOps** (View = **End-to-end journey**), incident **DOP-1001**.
2. **Lineage arrow chain** (core_ledger ➜ payments_bronze ➜ payments_silver ➜ payments_gold; **stale nodes red**) + **failure impact** (downstream datasets + consumers).
3. **Data Engineer** diagnostic recommendation.
4. **Approve & repair** — option **A**, tick approval, **Apply (simulated)**.
   > "Verification is **independent** — it re-checks raw telemetry against thresholds."
5. Point at the **recovery verdict** + **before/after** table:
   > "🟢 **Verified.** It can also say 🟠 **Mitigated** or 🔴 **Recovery failed** — it doesn't always claim success."
   *(Trick: option **B** → Mitigated, **C** → Recovery failed.)*

## 6. Recovery update + collaboration + delegation
1. Persona → **By role → Data Owner** (and **CSM**): show the **evidence-backed recovery update**.
2. Back to **Live Operations**:
   - **Collaboration**: post an update mentioning **@DataEngineer** → a notification is created.
   - **Delegation**: delegate the action → **assigned → Accept → Done**.
   - Switch role (sidebar **You are (role) = Data Engineer**) → show their **🔔 notification**.
   > "Collaboration and delegation live where the work happens — and context carries across roles."

## 7. Persona sweep (optional, 20s)
> "Switch **View → By role** to see the **same governed record** shaped to each person: Incident Manager, L1, L2/L3, Developer, CSM — and in DataOps, Data Engineer, Data Owner, Platform Engineer, Data Consumer."

---

## Closing line (15s)
> "We don't replace ServiceNow, Jira or observability — we're the **governed intelligence and resolution layer across them**: one context, controlled action and a **verified** outcome. One core, reusable across IT Ops, DataOps and beyond."

## The ask
> "I'd like 45 minutes with 3–5 practitioners — Incident Manager, Data Engineer, Data Owner — to compare it to what they do today and identify **which steps it would eliminate**. That tells us if this is a product, not just an architecture."

---

## Q&A — quick answers
- **"Is this AI making decisions?"** Deterministic graph + rules; suspected causes are human-confirmed. AI is used to reason over governed evidence.
- **"Live data?"** No — sample data, simulated actions. Real connectors (ServiceNow/Jira/observability/lineage) are the next step.
- **"Real-time?"** The stream auto-refreshes; a shared backend (pub/sub) is needed for true multi-user real-time.
- **"How is it hosted?"** Streamlit Community Cloud from a GitHub repo; no local install.
- **"Why should we trust it?"** Every claim carries an **evidence ledger** and independent verification with explicit thresholds.

## Honest limitations (say them before they're asked)
- Deterministic, not autonomous root-cause analysis.
- Sample data; no live connectors; no real logs/traces.
- Simulated remediation; SLA/KPI figures are scenario estimates.

---

## 5-minute version
1. Live Operations → **Replay → Reset → Play** (the story). *(60s)*
2. IT Ops → **End-to-end journey** → hypothesis cards + correlation → jump to DataOps. *(60s)*
3. DataOps → lineage + repair → **Apply** → **🟢 Verified**. *(90s)*
4. Live Ops → **@mention** + **delegate**. *(60s)*
5. Closing line + the ask. *(30s)*

## Do / Don't
- **Do** keep one incident as the spine; **Do** show the failure states; **Do** state what's simulated.
- **Don't** call it autonomous AI; **Don't** claim production scale or live data.
