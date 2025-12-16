# DESIGN SPECIFICATION: OPTIMIZED STATIC FREEZE PROTOCOL (V1.2)

**Document ID:** SPEC-V1.2-FREEZE-PROTOCOL  
**Date:** 2025-12-15  
**Context:** Project Prime Directive / `pd freeze` Command  
**Target Audience:** Implementation Engineers / UX Designers

---

## 1. Executive Summary & Rationale

The current static interview protocol ("What is the objective?", "What didn't work?", "What is the next action?") suffers from negative bias, redundancy, and high cognitive load. It fails to handle "clean exit" scenarios (success states) and often results in low-fidelity context capture.

While a fully dynamic AI-driven interview is the long-term ideal, the engineering cost is high. This specification defines an optimized **Static Interview Protocol** that delivers 80% of the dynamic value through strategic copywriting and psychological framing.

The new protocol leverages three key concepts derived from critical analysis:
1.  **Scope Drift Detection:** Capturing the delta between the *planned* task (TaskMaster) and the *actual* focus (Human).
2.  **The "Gotcha" Catch-All:** Framing the friction question to include technical debt and uncertainty, accommodating both failure and success states.
3.  **The 10-Second Ignition Constraint:** Forcing the "Next Action" to be atomic and low-friction to minimize re-entry cost.

---

## 2. The Optimized Script Protocol

The following table maps the database schema fields to the new optimized prompts. This text replaces the existing `typer.prompt` strings in `prime_directive/bin/pd.py`.

| DB Field | Old Prompt (Sub-Optimal) | **New Optimized Prompt** | **Design Intent & Psychological Mechanics** |
| :--- | :--- | :--- | :--- |
| `human_objective` | *"What is the primary objective of this session?"* | **"Context: What was your specific focus vs. the planned task?"** | **Drift Detection.** `tasks.json` knows the plan. The human knows the reality. This prompt invites the user to document the deviation ("I started on Auth, but ended up refactoring the Database"). |
| `human_blocker` | *"What didn't work or what is the key uncertainty?"* | **"Mental Cache: What is the key blocker, uncertainty, or 'gotcha'?"** | **State Agnosticism.** By adding "gotcha," we validate successful sessions where code works but is fragile. "Mental Cache" signals that this is a dump of temporary memory, not a formal bug report. |
| `human_next_step` | *"What is the next concrete action?"* | **"The Hook: What is the first 10-second action to restart?"** | **Granularity Constraint.** "Action" is vague. "10-second action" is a constraint. It forces the user to break down "Fix bug" into "Run grep on line 42," drastically lowering Monday morning activation energy. |
| `human_note` | *"Any additional notes or brain dump"* | **"Brain Dump: Any other context, warnings, or loose thoughts?"** | **Safety Net.** Retains the open-ended field for unstructured data that doesn't fit the structured buckets. |

---

## 3. Implementation Specification

### 3.1 Code Modification
**File:** `prime_directive/bin/pd.py`
**Function:** `freeze` command handler (lines ~290-330)

```python
    if not no_interview:
        if objective is None:
            # OPTIMIZATION 1: Capture Scope Drift
            # Don't ask "What is the task?" (Redundant). Ask "What did you actually do?"
            entered = typer.prompt(
                "Context: What was your specific focus vs. the planned task?",
                default="",
                show_default=False,
            )
            objective = entered.strip() or None

        if blocker is None:
            # OPTIMIZATION 2: Capture Hidden Debt ("Gotchas")
            # Covers Failure (Blocker), Uncertainty (Doubt), and Success (Tech Debt)
            entered = typer.prompt(
                "Mental Cache: What is the key blocker, uncertainty, or 'gotcha'?",
                default="",
                show_default=False,
            )
            blocker = entered.strip() or None

        if next_step is None:
            # OPTIMIZATION 3: The 10-Second Constraint
            # Forces atomic granularity. "Run test X" beats "Fix bug Y".
            entered = typer.prompt(
                "The Hook: What is the first 10-second action to restart?",
                default="",
                show_default=False,
            )
            next_step = entered.strip() or None

        if note is None:
            # OPTIMIZATION 4: Broad Safety Net
            entered = typer.prompt(
                "Brain Dump: Any other context, warnings, or loose thoughts?",
                default="",
                show_default=False,
            )
            note = entered.strip() or None
```

---

## 4. User Experience Simulation

### Scenario A: The "Clean Exit" (Success)
*Context: User finishes the Auth feature. Tests pass.*

*   **System:** `Context: What was your specific focus vs. the planned task?`
*   **User:** "Completed the JWT implementation as planned." (Easy confirmation).
*   **System:** `Mental Cache: What is the key blocker, uncertainty, or 'gotcha'?`
*   **User:** "No blockers, but the token expiration logic is a bit naive. That's a 'gotcha' for later." (**High Value: Captures technical debt**).
*   **System:** `The Hook: What is the first 10-second action to restart?`
*   **User:** "Merge the PR and pull main." (**Low Friction**).

### Scenario B: The "Rage Quit" (Failure)
*Context: User hits a wall with a segfault in a dependency.*

*   **System:** `Context: What was your specific focus vs. the planned task?`
*   **User:** "Tried to upgrade the library, but it broke everything." (Captures the Pivot/Failure).
*   **System:** `Mental Cache: What is the key blocker, uncertainty, or 'gotcha'?`
*   **User:** "Segfault in libz.so when calling init()." (Precise diagnosis).
*   **System:** `The Hook: What is the first 10-second action to restart?`
*   **User:** "Open issue #404 on their GitHub repo." (Atomic action, not "Fix the bug").

---

## 5. Strategic Benefits

1.  **Eliminates "Success Friction":** Users no longer feel prompted to invent failures when things go well. The "Gotcha" prompt validates their success while extracting deeper insight.
2.  **Enforces Granularity:** The "10-Second" constraint mechanically improves the quality of the `human_next_step` data, making the eventual SITREP significantly more actionable.
3.  **Zero Schema Changes:** This upgrade is purely logic-side. It improves the *quality* of the data stored in existing DB fields (`human_objective`, `human_blocker`, etc.) without requiring migrations or complex backend refactoring.