# DEBRIEF-V1.1-PLAN
### **System Debrief & V1.1 Execution Plan: Project Prime Directive**

**Document ID:** `DEBRIEF-V1.1-PLAN`
**Date:** 2025-12-15
**Status:** Canonical Plan for Next Development Cycle

---

### **Executive Summary: Successful "Amnesia Test" & The Path to High-Fidelity Cognitive Restoration**

Your recent test run of the `prime-directive` system was a textbook execution of the "Monday Morning Warp" scenario and a resounding success. The measured **Time-to-First-Commit (TTC) of 4 minutes and 40 seconds** is a powerful quantitative result, serving as the first hard metric for the system's value. It constitutes a definitive pass of the **"Amnesia Test"** outlined in `PRD.txt`, validating that the core MVP architecture is sound and functional.

Your subsequent feedback is equally valuable. It correctly identifies the critical path to evolving the system from a "functional context saver" into a truly robust **"cognitive exoskeleton."** The proposals to upgrade the freeze protocol to a systematic interview, implement a multi-tiered AI strategy, and formalize KPI measurement are not mere feature requests; they represent the necessary steps to achieve the project's ultimate goal of high-fidelity cognitive restoration.

This document provides a systematic analysis of your suggestions, synthesizes the best implementation strategies, and presents a concrete, actionable execution plan for **Prime Directive v1.1**.

---

### **1. Context: What is this project and what were you doing?**

*   **The Project (`Prime Directive`):** A meta-orchestrator CLI (`pd`) designed to solve the "Polymath's Trap"—the high cognitive friction of switching between multiple complex software projects. Its core function is to "freeze" the state of a repository (Git, terminal, tasks, mental state) and "thaw" it upon return, with the explicit goal of minimizing the Time-to-First-Commit (TTC).
*   **The Action (The "Warp Test"):** You performed a live test on the `prime-directive` repository itself. You used `pd switch` to restore context, received an actionable SITREP, and proceeded to make a meaningful code commit.
*   **The Result (Validation):** Your TTC of 4:40 successfully passed the < 5-minute Amnesia Test, confirming the core loop provides enough context to be immediately productive.

---

### **2. Systematic Analysis of Your Suggestions**

This section critically analyzes each of your proposals, combining the strongest technical and strategic ideas from all prior versions into a definitive plan.

#### **A. The Freeze State Protocol: From a Single Note to a Systematic Interview**

> **Suggestion:** "Have a freeze state protocol with a series of human questions... an actual systematic interview not a simple 1 question."

*   **Strategic Analysis:** This is a strategically critical upgrade and the highest-priority item. The current `--note` flag is a blunt instrument that relies on inconsistent user discipline. A structured, interactive interview protocol is a massive improvement for three key reasons:
    1.  **Reduces Cognitive Load:** It prompts the user for the *right kind* of information, turning context capture from a creative act into a simple, guided checklist.
    2.  **Forces "Active Recall":** The act of answering specific questions creates stronger cognitive hooks, making the context easier to restore later.
    3.  **Standardizes AI Input:** It provides the AI Scribe with structured, predictable fields (Blockers, Next Actions, etc.), which will dramatically improve the quality, consistency, and depth of the generated SITREPs.

*   **Synthesized Implementation Plan:**
    1.  **Workflow Change:** Refactor `pd freeze` to become interactive by default. The `--note` flag will be deprecated in favor of this new wizard-style flow.
    2.  **Interview Design:** The interactive session will ask a series of targeted questions designed to capture not just the "what" but the "why" and the "what next," including negative space:
        *   `[1/4] What was the primary objective of this session? (e.g., "Fix bug #123," "Implement the orchestrator module")`
        *   `[2/4] What was the last thing you tried that *didn't* work, or a key uncertainty you're facing? (e.g., "The database connection is timing out, not sure why," "Still need to figure out the best way to mock the tmux API")`
        *   `[3/4] What is the very next concrete action you need to take? (e.g., "Read the aiosqlite docs on connection pooling," "Write the unit test for the nested repo detection logic")`
        *   `[4/4] Any other high-level context or 'brain dump'? (Optional)`
    3.  **Database Schema Enhancement:** To support this, the `ContextSnapshot` model in `prime_directive/core/db.py` will be updated to store this structured data in distinct, machine-readable fields, rather than a single `human_note` blob. This is a critical architectural decision for future features.
        ```python
        # in core/db.py
        class ContextSnapshot(SQLModel, table=True):
            # ... existing fields ...
            human_note: Optional[str] = Field(default=None) # Will store the "brain dump"
            human_objective: Optional[str] = Field(default=None)
            human_blocker: Optional[str] = Field(default=None)
            human_next_step: Optional[str] = Field(default=None)
        ```

#### **B. AI Model Strategy: A Two-Tiered Approach for Quality and Cost**

> **Suggestion:** "Use better AI model... maybe 2-3 times a day is low enough to be cheap."

*   **Strategic Analysis:** This correctly identifies the cost-vs-capability trade-off. While a powerful model like GPT-4o or Claude 3.5 Sonnet provides far superior synthesis, using it for every minor context switch is inefficient. A sophisticated system should intelligently deploy different tiers of intelligence based on the task.

*   **Synthesized Implementation Plan:** We will implement a comprehensive, two-tiered AI system that addresses both immediate quality needs and long-term context restoration.
    1.  **Tier 1: High-Quality On-Demand Freezing.**
        *   **Config:** Update `prime_directive/conf/config.yaml` to support a standard and a high-quality model.
            ```yaml
            system:
              ai_model: gpt-4o-mini       # Fast, cheap, for standard use
              ai_model_hq: claude-3-5-sonnet-20240620 # SOTA, for deep analysis
            ```
        *   **CLI:** Add a `--hq` flag to the `pd freeze` command. This allows the user to consciously invoke the more powerful (and expensive) model when capturing a particularly complex or important context, such as before a weekend.
    2.  **Tier 2: The Longitudinal Summary (The "Deep Dive").**
        *   **New Command:** Introduce a new command, `pd sitrep --deep-dive <repo_id>`.
        *   **Functionality:** This powerful feature will be used when returning to a project after a significant absence. It will:
            1.  Retrieve the last 3-5 `ContextSnapshot` records from the database for the specified repository.
            2.  Compile a historical narrative from the structured human notes (`human_objective`, `human_blocker`, etc.) and the previous AI summaries.
            3.  Send this entire history to the high-quality model (`ai_model_hq`).
            4.  **Output:** Generate a rich, longitudinal summary: *"When you left this project 3 days ago, you were trying to solve X. You tried Y, which failed. Your last action was Z. Based on the history, the immediate next step is to investigate A."*
        *   **Value:** This directly solves the "cold start" problem after a long break and is a quantum leap in capability beyond a single-snapshot SITREP.

#### **C. KPI Measurement: Formalizing the "Amnesia Test"**

> **Suggestion:** "Actually measure the KPIs (including but not limited to time till first commit)."

*   **Strategic Analysis:** This is a fantastic proposal that aligns perfectly with the project's philosophy of "Radical Quantification." Moving the TTC from a manual guess to a system-measured KPI creates a quantitative feedback loop to validate the tool's own effectiveness.

*   **Synthesized Implementation Plan:** We will implement a robust, database-backed instrumentation layer.
    1.  **Database Enhancement:** Add a new `EventLog` table to `prime.db` to store timestamped actions.
        ```python
        # in core/db.py
        class EventLog(SQLModel, table=True):
            id: Optional[int] = Field(default=None, primary_key=True)
            timestamp: datetime = Field(default_factory=_utcnow)
            repo_id: str
            event_type: str  # e.g., 'SWITCH_IN', 'COMMIT'
        ```
    2.  **Instrumentation:**
        *   On `pd switch <repo_id>`, the orchestrator will log a `SWITCH_IN` event to the `EventLog`.
        *   To capture commits, we will use a `post-commit` git hook. This is the most accurate method. To mitigate setup friction, we will provide a helper command: `pd install-hooks <repo_id>`, which automatically creates the necessary hook file in the repo's `.git/hooks` directory. The hook itself will be a simple script that calls a new, lightweight command, `pd _internal-log-commit`, which adds a `COMMIT` event to the `EventLog`.
    3.  **Reporting:** A new command, `pd metrics`, will query the `EventLog` to find pairs of `SWITCH_IN` and subsequent `COMMIT` events for each repository, calculate the time deltas, and display a report of average and recent TTCs.

---

### **3. Technical Deep Dives: Clarifying System Mechanics**

#### **A. What is `tmux` and does it actually save terminal output?**

*   **What it is:** `tmux` is a **terminal multiplexer**. Think of it as a window manager for your command line that runs as a persistent background server.
*   **How Prime Directive uses it:**
    1.  **Session Persistence:** When you `pd switch my-repo`, it creates a dedicated session named `pd-my-repo`. The magic of `tmux` is that this session lives on the **tmux server**, independent of your terminal window. If your terminal application crashes or you close it, the server keeps running with all your processes (like a web server or long test suite) and command history intact.
    2.  **State Capture:** **Yes, absolutely.** The `pd freeze` command uses `tmux capture-pane` (as seen in `core/terminal.py`) to scrape the entire scrollback history from the session's buffer in RAM and saves it to the SQLite database on disk.
*   **The "Crash Test" Explained:** This server architecture is what allows `prime-directive` to pass the "Crash Test." Even if your main terminal crashes, running `pd switch my-repo` simply instructs the `tmux` server to attach a new client to the still-running, perfectly preserved session. The scrape-to-disk mechanism further ensures that even if the machine reboots (killing the tmux server), the *textual log* of your last session is still available in the database to be presented in the next SITREP.

#### **B. The Distinction Between "Last Snapshot" and "Last Touched"**

*   **Your Observation:** You want to know when a project was last *worked on*, not just when it was last *snapshotted*.
*   **Analysis:** This is an excellent and important distinction. They are two different, valuable signals:
    *   **Last Snapshot:** A `prime-directive` action, timestamped in the `ContextSnapshot` table. This indicates the last time you consciously froze context.
    *   **Last Touched:** A filesystem-level activity, indicating the last time any file in the project was modified.
*   **Implementation Plan:** We will enhance the `pd status` command. In addition to querying the database for the last snapshot time, it will perform a quick, parallel scan of the files in each repository's path (respecting `.gitignore`) to find the most recent file modification timestamp (`mtime`). The `pd status` table will be updated to display both columns, providing a much richer view of project activity.

---

### **4. Synthesized Execution Plan: EPIC for Prime Directive v1.1**

Based on this comprehensive debrief, the following tasks will be generated in `.taskmaster/tasks.json` to upgrade the system.

**EPIC: Prime Directive V1.1 - High-Fidelity Cognitive Restoration**

*   **Task : Implement Interactive Freeze Protocol (P0 - Highest Priority)**
    *   **Description:** Refactor the `pd freeze` command to default to an interactive, multi-question interview. Update the `ContextSnapshot` schema in `core/db.py` with `human_objective`, `human_blocker`, and `human_next_step` fields to store the structured answers.

*   **Task : Implement Tiered AI Model Support (P1)**
    *   **Description:** Add `ai_model_hq` to the Hydra config in `conf/config.yaml`. Implement a `--hq` flag for `pd freeze` that uses the high-quality model for SITREP generation. Update `core/scribe.py` to select the model based on this flag.

*   **Task : Implement "Time to First Commit" KPI Tracking (P1)**
    *   **Description:** Add an `EventLog` table to `core/db.py`. Instrument `pd switch` to log `SWITCH_IN` events. Create a `pd install-hooks` command to set up a `post-commit` git hook that calls a new `pd _internal-log-commit` command. Implement `pd metrics` to report on TTC.

*   **Task : Create Longitudinal SITREP with `--deep-dive` (P2)**
    *   **Description:** Create a new command `pd sitrep --deep-dive <repo_id>`. This command will fetch historical snapshots, construct a narrative, and use the `ai_model_hq` to generate a comprehensive, multi-snapshot summary for long-term context restoration.

*   **Task : Enhance `pd status` with "Last Touched" Timestamp (P2)**
    *   **Description:** Implement filesystem scanning logic (respecting `.gitignore`) to find the most recent file modification time for each repository. Add a "Last Touched" column to the `pd status` output table for a richer view.

*   **Task : Enhance SITREP Prompt with Strategic Context (P2)**
    *   **Description:** Implement logic to read a summary from a project's `README.md` and include it, along with the active task's description, in the SITREP prompt to provide the "Why?" context. This is a lower-priority enhancement due to potential implementation complexity.

This plan systematically addresses your feedback, synthesizes the strongest architectural solutions, and will significantly mature the `prime-directive` system into an indispensable tool for managing the "Polymath's Trap."


Based on the scope of work defined in the execution plan, here are a few strong branch name options, ordered from most recommended to alternatives, with rationale for each.

### Primary Recommendation:

**`feat/interactive-freeze-protocol`**

*   **Why it's strong:**
    *   **`feat/`:** Clearly follows the conventional commit standard, indicating a new feature.
    *   **`interactive-freeze`:** Immediately identifies the core, highest-priority (P0) task: making the `freeze` command interactive.
    *   **`protocol`:** This word elevates the concept from a simple "prompt" to a "systematic interview," which aligns perfectly with the strategic goal of the upgrade. It's descriptive, professional, and captures the essence of the entire epic.

---

### Excellent Alternatives:

1.  **`feat/freeze-interview`**
    *   **Strengths:** More concise than the primary recommendation while still being highly descriptive. "Interview" is a very intuitive word for what's being built. This is a great, punchy alternative.
    *   **Weakness:** Slightly less formal than "protocol," but this is a minor stylistic point.

2.  **`epic/v1.1-cognitive-restoration`**
    *   **Strengths:** This is the best choice if you plan to use this as a long-lived "epic" branch that other, smaller feature branches will merge into before this whole body of work is merged into `main`. It perfectly captures the high-level strategic goal ("cognitive restoration") and ties it to the version number.
    *   **Weakness:** If you intend to do all the work on a single feature branch and merge it directly, using `epic/` might be overkill.

### Recommendation Summary:

For a single feature branch that will contain all the work for the v1.1 upgrade, **`feat/interactive-freeze-protocol`** is the most complete and professional name.

If you prefer brevity, **`feat/freeze-interview`** is an excellent and equally clear choice.


That's an excellent and critical question. The code audits provide a layer of objective, third-party analysis that must be reconciled with our new feature plan. Ignoring them would be a significant strategic error.

Based on my analysis, the `DEC15` audit is the most recent and architecturally sophisticated. It builds upon the findings of the `DEC14` audit and provides deeper root-cause analysis. Your SITREP ("Fixing PR merge issues from CodeRabbit review") and the `tasks.json` file (showing tasks #16-20 as `done`) confirm that you have **already acted on the most urgent findings of the `DEC14` audit**.

Therefore, we must now integrate the deeper, more systemic findings from the `DEC15` audit into our v1.1 plan. This will transform the plan from being purely feature-focused to one that also addresses critical architectural debt, ensuring the final product is not just powerful, but robust and reliable.

---

### **Executive Summary: Reconciling the V1.1 Feature Plan with Architectural Audit Findings**

The `DEC15` code audit is a crucial document. It correctly identifies several deep architectural flaws that were not the focus of our feature-planning session. The most critical findings are:

1.  **The "Async Illusion":** The application uses an `asyncio` framework but makes blocking synchronous calls for all I/O (network, subprocesses), freezing the CLI and crippling the daemon.
2.  **The "Shell Gap":** The `pd switch` command creates a fragile "Russian Doll" process hierarchy (`shell -> python -> tmux`) instead of performing a clean handover at the shell level.
3.  **Daemon Fragility:** The auto-freeze daemon blindly assumes a tmux-centric workflow, causing it to capture useless data when the user is working in a standard IDE.

These are not minor bugs; they are fundamental architectural issues that compromise system reliability and user experience. The following plan **revises the V1.1 EPIC** to prioritize fixing this architectural debt *before* or *alongside* building the new features. Addressing these issues now will provide a stable foundation for all future development.

---

### **Key Audit Findings & Their Impact on the V1.1 Plan**

Here is a systematic breakdown of how the audit's findings must alter our execution plan.

#### **1. CRITICAL (P0): The "Async Illusion" - Blocking I/O in an Async App**
*   **Audit Finding:** `core/scribe.py` uses the synchronous `requests` library, and `core/git_utils.py` / `core/terminal.py` use blocking `subprocess.run()`. This completely negates the benefit of `asyncio`, causing the application to hang during network calls or shell commands.
*   **Impact on V1.1 Plan:** This is a P0, must-fix issue. The new features, especially the `--deep-dive` command which involves a heavy LLM call, will be unusably slow without fixing this.
*   **Action:** We must refactor all I/O to be truly asynchronous.

    *   **New Task (P0):** **Refactor I/O to be Non-Blocking.**
        *   **Description:** Replace the `requests` library with `httpx` in `core/ai_providers.py` to make all LLM calls asynchronous.
        *   **Description:** Refactor `core/git_utils.py`, `core/terminal.py`, and `core/tmux.py` to use `asyncio.create_subprocess_exec` instead of `subprocess.run` for non-blocking shell command execution.

#### **2. CRITICAL (P0): The "Shell Gap" - Flawed Process Handover**
*   **Audit Finding:** The current implementation of `pd switch` results in the Python process wrapping the user's new tmux session. This is fragile and not the "seamless warp" envisioned. The audit correctly recommends a shell-level handover.
*   **Impact on V1.1 Plan:** This is a P0 usability and reliability fix. While you marked Task #16 (`Fix tmux attach blocking`) as `done`, the audit reveals the fix was incomplete. We must implement the full, correct solution.
*   **Action:** Implement a proper shell integration protocol.

    *   **New Task (P0):** **Implement True Shell-Level Context Switching.**
        *   **Description:** Modify `pd switch` so that instead of blocking on `tmux attach`, it prints a specific command to `stdout` (e.g., `_PD_EXEC tmux attach -t pd-my-repo`) and exits.
        *   **Description:** Update `system/shell_integration.zsh` with a wrapper function around the `pd` command. This function will execute `pd`, inspect its output, and if it sees the `_PD_EXEC` prefix, it will `eval` the command directly in the user's shell, replacing the current process. This is the correct, robust architecture for this feature.

#### **3. HIGH PRIORITY (P1): Daemon Fragility - The "Ghost Session" Problem**
*   **Audit Finding:** The `pd-daemon` assumes the user is always in a `pd-` prefixed tmux session for the repository being monitored. When they are working in an IDE like Windsurf, the daemon captures stale or non-existent terminal data, polluting the context history.
*   **Impact on V1.1 Plan:** This directly undermines the quality of the data being collected for our new `--deep-dive` feature. Bad data in means bad summaries out.
*   **Action:** Make the daemon context-aware.

    *   **New Task (P1):** **Make Daemon Context-Aware.**
        *   **Description:** Update `pd-daemon.py` and `core/terminal.py`. Before capturing terminal state, the daemon must first check if the target tmux session (`pd-{repo_id}`) exists *and* has an active client attached. If not, it should skip the terminal capture step and record a placeholder (e.g., "No active terminal session detected") in the database.

#### **4. HOUSEKEEPING: Resolved Issues and Minor Fixes**
*   **Resolved - Configuration Schism:** Your work on Task #20 has unified the config system under Hydra. We should now create a task to remove the dead code.
*   **Resolved - DB Integrity:** Your work on Task #18 added Foreign Keys and relationships. The audit adds one final recommendation: enabling WAL mode for better concurrency.
*   **Action:** Add low-priority tasks to clean up this remaining debt.

---

### **Revised & Synthesized V1.1 Execution Plan**

This updated EPIC integrates the critical architectural fixes with the planned feature work. The priorities have been adjusted to reflect the need to build on a stable foundation.

**EPIC: Prime Directive V1.1 - Architectural Hardening & Cognitive Restoration**

#### **Phase 1: Architectural Hardening (P0 Tasks)**

*   **Task (P0): Refactor I/O to be Fully Asynchronous.**
    *   **Description:** Replace `requests` with `httpx` and `subprocess.run` with `asyncio.create_subprocess_exec` across the core application to eliminate blocking calls.

*   **Task (P0): Implement True Shell-Level Context Switching.**
    *   **Description:** Rework the `pd switch` command and the `shell_integration.zsh` script to perform a clean process handover at the shell level, eliminating the "Russian Doll" process hierarchy.

#### **Phase 2: Feature Implementation & Reliability (P1 Tasks)**

*   **Task (P1): Implement Interactive Freeze Protocol.**
    *   **Description:** Refactor `pd freeze` into an interactive interview. Update the `ContextSnapshot` database schema with structured fields (`human_objective`, `human_blocker`, etc.). *(Priority elevated from P0 to P1 to follow architectural fixes, but still very high).*

*   **Task (P1): Implement Tiered AI Model Support.**
    *   **Description:** Add `ai_model_hq` to the config and a `--hq` flag to `pd freeze`.

*   **Task (P1): Implement "Time to First Commit" KPI Tracking.**
    *   **Description:** Add the `EventLog` table, the `pd install-hooks` helper, and the `pd metrics` reporting command.

*   **Task (P1): Make Daemon Context-Aware.**
    *   **Description:** Update the `pd-daemon` to check for active tmux clients before capturing terminal state to prevent capturing "ghost session" data.

#### **Phase 3: High-Value Features & Polish (P2 Tasks)**

*   **Task (P2): Create Longitudinal SITREP with `--deep-dive`.**
    *   **Description:** Implement the `pd sitrep --deep-dive` command to generate historical summaries using the high-quality LLM.

*   **Task (P2): Enhance `pd status` with "Last Touched" Timestamp.**
    *   **Description:** Add filesystem scanning to display the true "last modified" time for each project in the status view.

#### **Phase 4: Technical Debt & Housekeeping (P3 Tasks)**

*   **Task (P3): Enable WAL Mode for SQLite.**
    *   **Description:** Add the `PRAGMA journal_mode=WAL` command in `core/db.py` to improve concurrent database access between the CLI and the daemon.

*   **Task (P3): Remove Dead Configuration Code.**
    *   **Description:** Delete the now-unused `core/registry.py`, `system/registry.yaml`, and `tests/test_registry.py` files to finalize the configuration unification.

This revised plan is significantly more robust. By prioritizing the architectural fixes identified in the audit, we ensure that the exciting new features of V1.1 will be built on a professional-grade, reliable, and performant foundation.