# Resolution Intelligence — 5-minute demo script (build v80)

**Setup, before they walk in (60 s)**
1. Open the cloud app: `https://itops-resolution-intelligence-7h4kpseynvdeka77mqw5dk.streamlit.app/`
2. Click **Demo → Reset demo** (fresh clock, clean thread). Leave the persona on **CIO**.
3. Browser zoom 100%, one window, one tab. Sidebar footer should read `build v80 · <sha>`.
4. Keep your next tab on **Analytics** so you can switch without typing a URL.

**Opening line (say it once, then stop talking about the problem)**

> "Two teams, one outage. IT Ops sees a payment service failing. Data sees a pipeline that ran
> late. Neither ticket can tell you the other exists — and neither can prove the fix worked.
> That's the gap this closes."

---

## 0:00–0:45 — the queue (Incidents page)

**Click:** nothing. Let them look at the list.

**Say:**
> "One queue for both worlds. Severity, where it sits, who owns it, how long is left, and — the
> column that matters — what we're currently waiting on. Two of these seven are one incident
> wearing two tickets; the ⇄ marks them."

**Click:** the **Board** toggle, then back to **List**.

**Say:**
> "Same data, two shapes: a scannable list for triage, cards for a wall display."

---

## 0:45–2:15 — the incident (open INC-8841)

**Click:** the **INC-8841** row ("Payment API failures — serving stale risk data").

**Point at the top bar (do not scroll yet):**
> "However far I scroll, the id, the verdict, the severity and the SLA stay with me. And there's
> exactly one primary action — the next thing this incident actually needs, not a menu of twelve."

**Point at the participants row:**
> "Who's on it, and the amber chip: we asked Platform Engineering for something 28 minutes ago and
> it's still open. That's the accountability gap made visible."

**Click:** **Open requests · 1** → show the request, **Done / Chase**, then collapse it.

**Click:** **Collaborate** (do not type, just show the form).
> "Any ask becomes a handoff with a deadline — who, what, how long — instead of a message that
> dies in a channel. It lands on the thread and it chases itself."

**Click:** **Confirm cause** (the primary button).
> "That took us to the stage that's blocking, not to a generic view."

**Scroll to the lifecycle, then the cross-domain thread.**
> "Six stages, one vocabulary across both domains. And the thread keeps evidence separate from
> inference: green `observed` means we recorded the signal; amber `inferred` is a hypothesis a human
> still has to confirm. We never dress a guess up as a root cause."

---

## 2:15–3:15 — verification and closure (the differentiator)

**Click:** nothing — scroll to the **bottom** of the workspace.

> "This is the part buyers don't have. Execution and verification are separate: applying a fix
> doesn't close anything. Verification is independent, and the verdict — Verified, Mitigated,
> Recovery failed, Inconclusive — comes from those checks, not from someone ticking 'done'."

**Click:** **Closure blocked · 2 requirement(s) open**.
> "Closure tells you exactly why it's refused: no verification record yet, and one open request.
> So 'closed' means something here — it's a record, not an opinion."

---

## 3:15–4:15 — analytics and the persona lens

**Click:** **Analytics** (sidebar).
> "Every number states its provenance: live numbers are computed from incidents on this system;
> illustrative ones are scenario estimates and labelled as such. Stage durations, verified closure
> rate, breach trend — no invented ROI."

**Click:** **Incidents** → sidebar **Demo persona** → **L1 Engineer**, then back to **CIO**.
> "Personas aren't decoration: they change what you land on and what you're allowed to execute.
> L1 gets the queue and read-only actions; a Data Owner lands on pipelines."

---

## 4:15–4:45 — the audit trail

**Click:** **Activity & audit** → **Verification records** tab, then **Handoffs**.
> "Every action, approval, handoff and verification is a record with who, when and what. That's
> what an auditor asks for on day two."

---

## 4:45–5:00 — close

**Click:** back to **Incidents**.

> "One queue, one thread across two teams, one lifecycle, and closure that has to be proven.
> It sits on top of ServiceNow and Monte Carlo — it doesn't replace them. Everything you saw is
> a prototype on sample data, which is exactly why the next step is a read-only connector to one
> real system."

---

## If they ask (one-line answers)

- **"Is this real?"** → "Sample data, simulated actions, labels say so everywhere. The connector is the next milestone, read-only first."
- **"Why not ServiceNow?"** → "It records tickets. It doesn't hold a cross-domain thread, and it doesn't gate closure on independent verification."
- **"What if the fix fails?"** → "Verdict says Recovery failed or Inconclusive, the incident stays open, closure is refused. Show it if asked."
- **"Is my data safe?"** → "Prototype: local sample data, no customer data, no integrations, no auth yet — production hardening is milestone three."

## If a click misbehaves

1. **Nothing opens** → click the row again; if still stuck, press **← All incidents** and re-open.
2. **Filters look empty** → **Reset filters**; the list is never empty, it's filtered.
3. **It feels slow** → keep talking through the concept; Streamlit Cloud wakes on demand.
