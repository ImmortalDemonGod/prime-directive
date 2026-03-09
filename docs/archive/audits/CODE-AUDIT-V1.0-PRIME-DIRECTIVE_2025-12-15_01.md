# COMPREHENSIVE CODE AUDIT: PRIME DIRECTIVE V0.1.0

**Date:** 2025-12-15
**Target:** `prime-directive` Repository
**Auditor:** Principal Software Architect
**Version:** 1.0 (Synthesized Analysis)

---

## 1. Executive Summary

**Verdict:** **Functional Prototype with Architectural Debt**

The `prime-directive` codebase successfully implements the core logic of context preservation (Git, Terminal, Task, AI Summary). It achieves the primary user story—capturing state and generating a "SITREP"—with a high degree of logical correctness. The domain modeling in `core/` is robust, modular, and testable.

However, the system falls short of "Enterprise Reliability" due to three critical architectural deviations:
1.  **The Async Illusion:** The application architecture is built on `asyncio` (`aiosqlite`), but critical I/O paths (Network/AI, Subprocess/Git) are synchronous and blocking. This renders the async architecture performative rather than functional, leading to CLI freezes.
2.  **The Shell Gap:** The "Seamless Warp" experience is compromised by incomplete shell integration. The Python process currently "swallows" the user session rather than handing control back to the shell, diverging from the Task #13 specification.
3.  **Daemon Fragility:** The background daemon relies on brittle assumptions about the user's workflow (specifically, that they are *always* inside a named tmux session), which causes it to fail silently in common IDE environments.

**Readiness:** **Beta / Developer Preview.** Do not deploy to a wider team until the Blocking I/O and Shell Integration issues are resolved.

---

## 2. Architectural Analysis

### 2.1 The "Client-Daemon" Model
*   **Design:** A CLI (`pd`) for user interaction and a Daemon (`pd-daemon`) for background monitoring.
*   **Implementation:** Both share the same core logic (`core/`).
*   **Critical Finding:**
    *   **Locking Risk:** Both processes access the SQLite database `data/prime.db` simultaneously. While `aiosqlite` is used, the code does not explicitly enable **WAL (Write-Ahead Logging)** mode in `core/db.py`. Without WAL, a long-running Daemon write (freeze) could lock the DB while the user runs `pd status`, triggering a `database is locked` error.

### 2.2 The Concurrency Model (Async vs. Sync)
*   **Design:** Asyncio event loop used in `pd.py` and `pd_daemon.py`.
*   **Reality:**
    *   **Database:** Async (`aiosqlite`). ✅
    *   **AI Engine (`core/scribe.py`):** **Sync (`requests`)**. ❌ *Critical Bottleneck.*
    *   **Git/Terminal (`subprocess`):** **Sync**. ❌ *Blocker.*
*   **Impact:** When `pd freeze` runs, the `asyncio` loop is blocked for 3-10 seconds while waiting for OpenAI/Ollama. In the CLI, this is annoying. In the Daemon, this is fatal—it stops the `watchdog` observer from processing file events during that window.

### 2.3 Configuration Management
*   **Design:** Hierarchical configuration.
*   **Reality:** **Schism Detected.**
    *   **Modern Path:** `conf/config.yaml` loaded via Hydra in `bin/pd.py`.
    *   **Legacy Path:** `system/registry.yaml` loaded via `core/registry.py` (Pydantic).
*   **Impact:** `core/registry.py` is effectively dead code, yet it remains in the codebase and tests (`tests/test_registry.py`), creating confusion about the Source of Truth. This is an incomplete refactor of Task #20.

---

## 3. Component-Level Deep Dive

### 3.1 The Data Layer (`core/db.py`)
*   **Schema:** `Repository` (metadata) and `ContextSnapshot` (state).
*   **Analysis:**
    *   **Strengths:** Uses `SQLModel` for clean, typed schema definition. Correctly enforces Foreign Keys via event listeners.
    *   **Weaknesses:**
        *   **Missing Indexing:** As noted in V1, there is no `TaskIndex` or flattened search table. Global search (`pd search "bug"`) is impossible without O(N) file parsing.
        *   **Missing Migrations:** Uses `create_all`, which works for V1 but will cause data loss or errors if the schema changes in V1.1. No `alembic` configuration is present.

### 3.2 The Intelligence Layer (`core/scribe.py`)
*   **Logic:** Generates SITREP using Ollama or OpenAI.
*   **Analysis:**
    *   **Strengths:** Robust prompt engineering (integrates Task, Git, Terminal).
    *   **Weaknesses:**
        *   **Retry Logic:** Uses a manual `for attempt in range` loop with `time.sleep`. This blocks the thread. It should use `tenacity` (Task #17) for non-blocking, declarative retries.
        *   **Serial Fallback:** Tries Ollama -> Waits -> Fails -> Tries OpenAI. This cumulative latency (5s + 10s) makes the "Freeze" feel very slow.

### 3.3 The Daemon (`bin/pd_daemon.py`)
*   **Logic:** Watches filesystem -> Triggers `freeze_logic`.
*   **Analysis:**
    *   **Critical Flaw (The "Ghost Session"):** The daemon calls `capture_terminal_state` in `core/terminal.py`. This function executes `tmux capture-pane -t pd-{repo_id}`.
    *   **Scenario:** A user opens the repo in VS Code (Windsurf). They edit files. The daemon detects changes. It tries to capture the tmux pane `pd-repo`. *It does not exist* (because they are in VS Code) or it is *stale* (an old session).
    *   **Result:** The snapshot contains "No tmux session found" or irrelevant data, actively degrading the quality of the SITREP. The Daemon blindly assumes a Tmux-only workflow.

### 3.4 The Orchestrator (`core/orchestrator.py`)
*   **Logic:** `detect_repo` -> `freeze` -> `switch`.
*   **Analysis:**
    *   **Strength:** `detect_current_repo_id` correctly implements longest-prefix matching, handling nested repos (e.g., monorepos) correctly.
    *   **Weakness:** The Handover mechanism. `run_switch` calls `ensure_session(..., attach=True)`. This runs `subprocess.run(["tmux", "attach"])`.
    *   **Impact:** The `pd` Python process *remains alive* as the parent of the tmux client. If the user kills the parent shell, the python script dies. This is a fragile "Russian Doll" process hierarchy compared to `exec`-ing or using shell integration.

### 3.5 Tooling Integrations (`core/windsurf.py`)
*   **Logic:** Launches editor.
*   **Critical Flaw:** Hardcoded Flags.
    ```python
    subprocess.Popen([editor_cmd, "-n", repo_path])
    ```
    The `-n` flag is specific to VS Code/Windsurf. If a user sets `editor_cmd: vim` in `config.yaml`, this command crashes (`vim: invalid option -n`).

---

## 4. Execution Trace: "The Monday Morning Warp"

**Scenario:** User types `pd switch rna-predict`.

1.  **Boot:** `bin/pd.py` loads Hydra config.
2.  **Detection:** Identifies current directory as `prime-directive`.
3.  **Freeze (`prime-directive`):**
    *   `get_status` (Git): **BLOCKING**.
    *   `capture_terminal` (Tmux): **BLOCKING**.
    *   `get_active_task` (File I/O): **BLOCKING**.
    *   `scribe.generate` (Network): **BLOCKING**. *CLI freezes for ~3-8s.*
    *   `db.add` (SQLite): Async. Snapshot Saved.
4.  **Warp (`rna-predict`):**
    *   `orchestrator` prints "WARPING...".
    *   `tmux.ensure_session` creates detached session `pd-rna-predict`.
    *   `windsurf.launch` opens IDE.
5.  **Thaw:**
    *   Reads DB. Prints SITREP table.
6.  **Handover (The Failure Point):**
    *   Python calls `tmux attach`.
    *   User enters tmux.
    *   *System Check:* `system/shell_integration.zsh` has no hook to handle this. The user is technically nested inside a Python subprocess.

---

## 5. Risk Assessment

| Risk Category | Severity | Description |
| :--- | :--- | :--- |
| **Performance** | **High** | Synchronous Network I/O in `scribe.py` freezes the application and blocks the Daemon watchdog loop. |
| **Usability** | **High** | Broken Shell Integration means `pd switch` creates a fragile process hierarchy rather than a true shell context switch. |
| **Reliability** | **Medium** | Lack of WAL mode in SQLite risks locking collisions between Daemon and CLI. |
| **Data Integrity** | **Medium** | Lack of Alembic migrations means schema changes require database deletion. |
| **Edge Case** | **Medium** | Hardcoded `-n` flag in editor launcher breaks non-VSCode editors. |

---

## 6. Recommendations & Action Plan

### Priority 1: Fix the I/O Architecture
*   **Action:** Refactor `core/ai_providers.py` and `core/scribe.py` to use `httpx` instead of `requests`.
*   **Code Change:** Make `generate_sitrep` an `async def`.
*   **Benefit:** Enables non-blocking operation, crucial for the Daemon's stability.

### Priority 2: Fix Shell Integration
*   **Action:** Modify `bin/pd.py` to *exit* with a specific status code or print a token file if a switch is needed.
*   **Action:** Update `system/shell_integration.zsh` to trap this exit/token and execute `tmux switch-client` or `tmux attach` *at the shell level*.
*   **Benefit:** Removes the fragile "Python wrapping Tmux" hierarchy.

### Priority 3: Daemon Context Awareness
*   **Action:** Update `pd_daemon.py` / `core/terminal.py`. Before capturing, check if the `pd-{repo_id}` tmux session has active clients or recent activity time. If not, skip terminal capture or capture a generic warning.
*   **Benefit:** Prevents "ghost session" data from polluting the SITREP when working in IDEs.

### Priority 4: Clean Up Technical Debt
*   **Delete:** `core/registry.py`, `system/registry.yaml`, and `tests/test_registry.py`.
*   **Refactor:** `core/windsurf.py` to accept `editor_args` from config, defaulting to `[]` or `["-n"]` only if the editor is known to support it.
*   **Database:** Enable WAL mode in `core/db.py`:
    ```python
    await conn.execute("PRAGMA journal_mode=WAL")
    ```

## 7. Final Conclusion

The `prime-directive` v0.1.0 codebase is a **sophisticated proof-of-concept**. It correctly models the domain and solves the core problem of context preservation. However, its implementation details—specifically the synchronous I/O and process management—betray its prototype nature. It requires one focused refactoring sprint (focused on Async I/O and Shell Integration) to be considered truly production-ready.