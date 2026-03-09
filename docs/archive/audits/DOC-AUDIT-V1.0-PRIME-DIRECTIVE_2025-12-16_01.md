# Technical Documentation Audit: Prime Directive v0.1.0

**Date:** 2025-12-16
**Target:** `prime-directive` Repository
**Auditor Role:** Senior Systems Architect
**Verdict:** **Critical Documentation Lag (Docs v1.0 vs Code v1.2)**

---

## 1. Executive Summary

A comprehensive forensic audit of the `prime-directive` repository reveals a sophisticated, high-velocity codebase that has significantly outpaced its documentation. While the application architecture (Async I/O, SQLModel, Hydra) is robust and modern, the user-facing documentation (`README.md`, `docs/`) contains critical inaccuracies that render the tool unusable for new users without source code inspection.

**Key Risks Identified:**
1.  **Installation Failure:** The documentation omits mandatory shell integration steps, breaking the core context-switching functionality.
2.  **Configuration Hazard:** The default configuration file contains hardcoded user-specific paths (`/Users/tomriddle1/...`) which will cause immediate runtime crashes for any other user.
3.  **Workflow Divergence:** The documentation describes a flag-based CLI workflow, while the code enforces an interactive interview protocol.
4.  **"Ghost Code" & Process Failure:** Completed tasks tracked in `tasks.json` do not match the filesystem state, resulting in dead code shipping with the product.

---

## 2. Architecture & Implementation Reality

To understand the documentation gaps, we must first establish the *actual* state of the codebase based on file analysis.

*   **Core Framework:** Python 3.11+ using `Typer` for CLI and `SQLModel` + `aiosqlite` for asynchronous persistence.
*   **Configuration:** Unified under **Hydra** (`prime_directive/conf/config.yaml`).
*   **Process Model:** A split-process architecture.
    *   **Client (`pd`):** Handles user interaction and orchestrates logic.
    *   **Shell Handover:** Uses a specific protocol where the Python process returns **Exit Code 88**. The parent shell (ZSH) must trap this code to execute `tmux switch-client`.
    *   **Daemon (`pd_daemon`):** Background file watcher for auto-freezing context.

---

## 3. Critical Gap Analysis: Documentation vs. Codebase

### 3.1 Installation & Onboarding (Blocker Severity)

The current onboarding guide ensures a broken installation.

| Component | Documentation Claim (`README.md`) | Codebase Reality | Impact |
| :--- | :--- | :--- | :--- |
| **Shell Integration** | Mentions "Tmux Integration" generally. | `system/shell_integration.zsh` contains the logic to trap Exit Code 88 and perform the tmux switch. | **Critical.** The `README` does not instruct the user to `source` this file. Without it, `pd switch` will run logic but fail to actually switch the terminal session. |
| **Configuration** | Points users to edit `conf/config.yaml`. | `conf/config.yaml` contains: `path: /Users/tomriddle1/prime-directive`. | **High.** Users following the guide will experience immediate crashes as the tool tries to access a non-existent directory on their machine. |
| **Dependency Setup** | `CONTRIBUTING.md` says: `uv pip install -e ".[dev]"` | `pyproject.toml` defines test dependencies under `[test]`, not `[dev]`. | **Medium.** New contributors cannot install the environment following the guide. |

### 3.2 Core Workflow Divergence (High Severity)

The primary value proposition of the tool—the "Freeze Protocol"—has changed paradigms.

*   **Documentation:** Describes a **Transactional Model**.
    *   Command: `pd freeze my-repo --note "Fixing bugs"`
    *   Claim: *"The --note flag is MANDATORY"*
*   **Codebase (`bin/pd.py`):** Implements an **Interactive Interview Model**.
    *   Behavior: The command defaults to a 4-step wizard:
        1.  `Context: What was your specific focus?`
        2.  `Mental Cache: What is the key blocker?`
        3.  `The Hook: First 10-second action?`
        4.  `Brain Dump:`
    *   **Discrepancy:** The `--note` flag is now optional/secondary (`--no-interview` flag required to bypass). The internal docstrings (`pd freeze --help`) are also outdated, repeating the "mandatory note" claim.

### 3.3 "Hidden" Features (Discoverability)

Approximately 40% of the tool's v1.2 functionality is undocumented.

1.  **Tiered AI (`--hq`):** The code supports `pd freeze --hq` to use a more expensive/capable model (configured via `ai_model_hq`). This is absent from docs.
2.  **Longitudinal Analysis:** `pd sitrep --deep-dive` generates history-based narratives. This key feature is invisible to users.
3.  **Metrics & KPIs:** `pd metrics` (Time-to-First-Commit tracking) and `pd install-hooks` are fully implemented but undocumented.
4.  **Budgeting:** `pd ai-usage` tracks API costs, but users are not told this command exists or how to configure the budget limits in `config.yaml`.

---

## 4. Project Hygiene & Technical Debt

### 4.1 The "Ghost Code" Anomaly
The project tracking file `.taskmaster/tasks/tasks.json` marks **Task #36 (Remove Dead Configuration Code)** as `done`.

*   **Verification:**
    *   `prime_directive/core/registry.py` (Old Pydantic config) **Exists**.
    *   `prime_directive/system/registry.yaml` (Old Config file) **Exists**.
*   **Conclusion:** The task was marked complete without verification. This creates a "Split-Brain" configuration risk where users might edit `registry.yaml` expecting results, while the code actually uses `conf/config.yaml`.

### 4.2 Packaging "Split-Brain"
The project uses three conflicting methods for dependency definition:
1.  `pyproject.toml` (Modern, used by `uv`).
2.  `setup.py` (Legacy).
3.  `requirements.txt` (Redundant).
*   **Risk:** `setup.py` is often ignored by modern tools but picked up by others, leading to inconsistent environments.

### 4.3 Containerization Failure
*   **File:** `Containerfile`
*   **Content:** `FROM python:3.7-slim`
*   **Code Requirement:** `pyproject.toml` specifies `requires-python = ">=3.11"`.
*   **Result:** The Docker build is guaranteed to fail.

---

## 5. Remediation Plan

To resolve these discrepancies, the following actions are recommended in order of priority.

### Phase 1: Critical User Unblocking (Immediate)
1.  **Fix Installation Guide (`README.md`):**
    *   Add the mandatory step: `source /path/to/prime_directive/system/shell_integration.zsh` in `.zshrc`.
    *   Explain *why* (Exit Code 88 protocol) so users can debug it.
2.  **Sanitize Configuration:**
    *   Remove `/Users/tomriddle1` paths from `prime_directive/conf/config.yaml`. Replace with generic placeholders or use `~` expansion consistently.
3.  **Update Config Docs:**
    *   Explicitly tell users to copy the default config to `~/.prime-directive/config.yaml` (and ensure `pd.py` loads from there).

### Phase 2: Documentation Alignment
4.  **Rewrite "Quick Start":**
    *   Remove the `--note` example. Replace with a walkthrough of the **Interactive Interview**.
5.  **Update Command Reference:**
    *   Add `pd sitrep --deep-dive`, `pd metrics`, `pd ai-usage`, and `pd install-hooks`.
    *   Update `pd freeze` help text docstrings in `bin/pd.py` to reflect optional flags.

### Phase 3: Codebase Hygiene
6.  **Execute Task #36 (For Real):**
    *   Delete `prime_directive/core/registry.py` and `prime_directive/system/registry.yaml`.
    *   Delete `main.py`, `prime_directive/base.py`, and `prime_directive/cli.py` (unused template boilerplate).
7.  **Fix Packaging:**
    *   Delete `setup.py` and `requirements.txt`. Rely solely on `pyproject.toml`.
    *   Update `Containerfile` to `FROM python:3.11-slim`.