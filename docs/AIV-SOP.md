# AIV Standard Operating Procedure (SOP)

This document formalizes the **Architect-Implementer-Verifier (AIV)** model, specifically outlining the verification protocols for human verifiers. The goal is to eliminate "winging it" by requiring concrete evidence for every claim made by the Implementer (AI or Human).

## The Verifier's Role

The Verifier is the last line of defense. Your job is not to trust, but to **validate**. If the Implementer claims a task is done, you must prove it.

---

## 1. Clean Tree Check (Static Verification)

**When to use:** Refactors, deletions, file movements, or "cleanup" tasks.

**Procedure:**
1.  **Do not trust `git status` alone.** A clean git status only means nothing is *currently* modified; it doesn't prove the right files were deleted or kept.
2.  **Manually inspect the file tree.** Use your IDE's file explorer or `ls -R` / `tree` to confirm the actual state of the filesystem.
    *   *Example:* If the task was "Remove legacy config files," verify `core/registry.py` is actually gone.
    *   *Example:* If the task was "Move logic to `new_module.py`," verify `new_module.py` exists and contains the code.
3.  **Check for "ghost" files.** Ensure no `__pycache__`, `.DS_Store`, or empty directories remain if they were part of the cleanup scope.

**Acceptance Criteria:** The filesystem structure exactly matches the architectural intent.

---

## 2. Runtime Check (Dynamic Verification)

**When to use:** New features, bug fixes, CLI command updates, or script changes.

**Procedure:**
1.  **Run the code.** Never accept a code change without execution.
2.  **Use specific flags/arguments.** Do not just run the default command; test the specific edge cases or flags modified.
    *   *Example:* If `pd freeze` was updated to support `--no-interview`, run:
        ```bash
        pd freeze my-repo --no-interview --note "Test run"
        ```
3.  **Verify Output.** Check stdout/stderr for expected messages, error codes, and formatting.
    *   *Example:* Does the `--help` text match the new arguments?
    *   *Example:* Did the script exit with code 0 on success and non-zero on failure?

**Acceptance Criteria:** The software behaves exactly as specified in the PRD/Ticket when executed.

---

## 3. State Check (Data Verification)

**When to use:** Database schema changes, logging logic updates, state machine transitions, or persistent storage modifications.

**Procedure:**
1.  **Inspect the persistence layer.** Do not rely on "Success" messages in the UI/CLI.
2.  **Query the database.** Use `sqlite3`, `pgadmin`, or a script to dump the relevant table rows.
    *   *Example:* If `pd freeze` logs a snapshot, run:
        ```bash
        sqlite3 ~/.prime-directive/data/prime.db "SELECT * FROM context_snapshots ORDER BY timestamp DESC LIMIT 1;"
        ```
3.  **Verify Data Integrity.** Check that fields are populated correctly (no NULLs where data belongs) and relationships (foreign keys) are valid.
    *   *Example:* Did the `cost_estimate_usd` column get populated with a non-zero value?

**Acceptance Criteria:** The persistent state (DB, files, logs) accurately reflects the transaction that just occurred.
