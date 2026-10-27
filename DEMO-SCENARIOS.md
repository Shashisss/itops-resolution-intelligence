# Repeatable demo scenarios (v81)

Two 90-second scenarios you can run back to back, in front of any audience.

**Why they repeat:** every browser session works on its own copy of the sample database. Execute,
verify, close — then **refresh the browser** and everything is back to the seeded state. Nothing is
written to the shared database, so there is no reset step and no chance of demoing a half-closed
incident.

The sidebar says `Demo session · anything you click is discarded on refresh` while this is active.
(`RI_DEMO_MODE=0` turns it off for anyone who wants the changes to persist.)

---

## Scenario 1 — "a partial fix is not a closure" (DOP-1001, 90 s)

Teaches: verification drives state; Mitigated ≠ Verified; closure is gated.

1. **Incidents → click row DOP-1001** (`payments_bronze_ingest failed — source schema drift`).
2. Point at the top bar: `DOP-1001 · Investigating · Critical · Correlate · 3h 9m left`.
3. Click the primary action **Confirm cause** → lands on the guided view at Correlate.
4. Click step **Act** in the progress strip (Detect · Correlate · Coordinate · **Act** · Verify · Close).
5. Choose **B · "Replay without a contract update"**.
6. Tick **I approve this action** → click **Apply selected repair (simulated)**.
   → verdict becomes **Mitigated**: some checks pass, some fail. Say: *"The repair ran; the evidence
   says it did not fully work. We do not call that fixed."*
7. The Apply button is now disabled with *"Execution recorded · B · authoritative verdict Mitigated"* —
   say: *"One execution per record. You cannot re-run the same repair and hope for a better result."*
8. Scroll to the bottom → **Closure blocked** → open it: *"Authoritative verdict is Mitigated —
   closure requires Verified"*, plus the failing checks listed.
9. Now the honest second attempt: go back to **Act**, select **A · "Reconcile source schema …"**,
   tick approval, click **Execute as a new attempt** → verdict **Verified**.
10. **Close incident** appears in the top bar (or use the gate) → click it → incident closes on the record.
11. **Refresh the browser** → DOP-1001 is back to Investigating. Say: *"and that's why it's safe to
    demo — refresh undoes the story."*

**If they ask why attempt 2 is allowed:** the first repair is kept as an attempt with its own verdict;
a new attempt is a new recorded execution, not an edit of history.

---

## Scenario 0 — the button that always knows the next step (INC-8850, 40 s)

The primary action is derived from evidence, so it advances as you do the work:

1. **Incidents → INC-8850** → the button reads **Confirm cause**.
2. Primary action → guided view at Correlate → **Confirm top hypothesis as root cause**.
3. The button is now **Bring in owner** (stage chip moves to *Coordinate*). Say: *"it doesn't leave me
   on a step I already finished."*
4. **Bring in owner** → guided Coordinate → **Collaborate** → pick a team, write the ask, 30 min →
   **Send request**. The button becomes **Execute fix** and `Open requests · 1` appears.
5. **Execute fix** → choose **A**, approve, **Apply selected action** → verdict **Verified**.
6. The button now reads **See blockers** — because the request is still open. Open **Open requests →
   Done** and it becomes **Close incident**. Click it: closed on the verified record.

Refresh → back to the start.

## Scenario 2 — "two teams, one thread" (INC-8841 + DOP-1001, 90 s)

Teaches: cross-domain correlation, collaboration with a clock, evidence vs. inference.

1. **Incidents → click row INC-8841** (`Payment API failures — serving stale risk data`).
2. Point at the participant strip and the amber chip `Waiting 28 min · Platform Engineering`.
3. Click **Open requests · 2 · overdue** → two requests: one *acknowledged* (Platform Engineering,
   26 min) and one **OVERDUE** (Data Platform, 55 min, sent but never acknowledged). Show **Done**
   (moves it to Completed with **Reopen**) and **Chase**, then collapse.
4. Click **Collaborate**:
   - Who: `Platform Engineering` (pre-selected)
   - What: `Confirm contract v4 is deployed`
   - Expected back in: `30 min` · Channel: `Teams` · **Send request**
   → say: *"An ask with a deadline and a named owner. It is on the thread, it is visible in the queue,
   and it will show as overdue if it slips."*
5. Scroll to **Cross-domain resolution thread**: point at green `observed` vs amber `inferred`.
   *"Observed is a signal we recorded. Inferred is a hypothesis a human still has to confirm — we
   never present a dependency as a proven root cause."*
6. Click **Next →** in the queue → you land on the DataOps side of the same story (or press
   `← Previous` to return). Say: *"Same thread, other domain, no copy-paste."*

---

## Preparation (10 seconds, optional)

- Persona: **CIO** for the portfolio view, **L1 Engineer** if you want to show the read-only gate.
- If a demo ever looks stale, **refresh** — that is the reset.
- If a click misfires: click the row again, or press **← All incidents**.

## Which incident gives which verdict (so nothing surprises you)

| Incident | Option A | Option B | Option C |
|---|---|---|---|
| DOP-1001 | Verified | **Mitigated** | Recovery failed |
| INC-8841 | Verified | **Mitigated** | Recovery failed |

Use **B** when you want a partial outcome, **A** for the clean path, **C** to show a failed recovery
that keeps the incident open.
