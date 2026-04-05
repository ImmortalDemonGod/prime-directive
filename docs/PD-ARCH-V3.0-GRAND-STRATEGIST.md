# Prime Directive V3.0: The Grand Strategist Protocol

## Design Specification — Comprehensive Technical Documentation

**Document Version:** 3.0  
**Date:** 2025-03-08  
**Status:** Authoritative Implementation Specification  
**Supersedes:** PD-ARCH-V2.1-STRATEGIST_2025-12-16.md  

---

## Document History

| Version | Date | Description |
|---------|------|-------------|
| V1.0 | 2025-12-14 | Initial implementation: single-repo freeze/switch with Ollama SITREP |
| V1.1 | 2025-12-15 | Audit-driven stabilization: async I/O, shell exit-code handshake, budget enforcement |
| V1.2 | 2025-12-16 | Interactive freeze protocol, tiered AI, deep-dive SITREP, TTC metrics |
| V2.1 | 2025-12-16 | Design proposal: "Grand Strategist" portfolio orchestration (unimplemented) |
| **V3.0** | **2025-03-08** | **This document: Synthesized specification combining V1.x proven foundation with V2.1 strategic vision, informed by critical analysis of both** |

---

## 1. Executive Summary

### 1.1 The Problem

Modern software development rarely involves a single repository. Developers routinely maintain 3–10+ projects simultaneously — a primary research project, supporting infrastructure, legacy maintenance, documentation sites, tooling. The cognitive cost of context-switching between these projects is the single largest source of wasted developer time, yet no existing tool addresses it at the portfolio level.

Prime Directive V1.x solved the **tactical** problem: preserving and restoring context for individual repositories through automated snapshots (freeze/thaw), AI-generated situation reports (SITREPs), and seamless tmux/editor session management. This has been validated through real-world usage — the database contains months of operational snapshots demonstrating that developers can resume work on any project within minutes of switching context.

However, V1.x cannot answer the **strategic** question: *"I have 6 projects, limited time, and a Friday deadline — what should I work on right now, and why?"* This is the problem that the Grand Strategist Protocol solves.

### 1.2 The Solution

This document specifies **Prime Directive V3.0**, a portfolio-wide intelligence layer built on top of the proven V1.x foundation. V3.0 introduces a new CLI command — `pd overseer` — that synthesizes tactical project state (from existing V1.x snapshots), portfolio structure (from a new `empire.yaml` configuration), and the developer's current strategic goals (from a human-readable `strategy.md`) into a single, prioritized, actionable directive.

The design is a **deliberate synthesis** of two prior approaches, informed by a critical analysis of their respective strengths and weaknesses:

- **From V1.x (proven):** The async runtime, SQLite/SQLModel database, Hydra configuration, httpx networking, shell integration, interactive freeze protocol, tiered AI model support, and budget enforcement. These are not redesigned — they are extended.
- **From V2.1 (proposed):** The portfolio structure model (`empire.yaml`), temporal strategy layer (`strategy.md`), cost-aware heartbeat caching, deterministic scoring algorithm, and LLM-as-validator architecture. These are refined based on critical review.
- **New in V3.0:** Explicit handling of V2.1's identified weaknesses — reduced configuration burden via progressive onboarding, graceful degradation when portfolio metadata is incomplete, and a migration path from V1.x that requires zero breaking changes.

### 1.3 Design Constraints

This specification operates under the following non-negotiable constraints:

1. **Zero breaking changes to V1.x.** All existing commands (`pd freeze`, `pd switch`, `pd sitrep`, `pd metrics`, `pd doctor`, `pd status`, `pd list`, `pd ai-usage`, `pd install-hooks`) must continue to work identically. V3.0 is purely additive.
2. **The scoring algorithm is deterministic.** The LLM validates and enriches, but does not decide. A developer must be able to predict the ranking by reading the algorithm.
3. **Cost ceiling.** The `pd overseer` command must respect the existing `ai_monthly_budget_usd` budget. Heartbeat generation during `pd freeze` must use the cheap model (`ai_model`), not the expensive one (`ai_model_hq`).
4. **Offline-capable core.** The scoring pipeline (Stages 1–4) must produce a useful ranking even when no LLM is available. LLM validation (Stage 5) is an enhancement, not a requirement.
5. **Single-developer focus.** V3.0 is designed for a solo developer managing multiple projects. Team/multi-user features are explicitly out of scope.

---

## 2. Critical Analysis of Prior Versions

This section documents the verified strengths and weaknesses of each prior version. Every claim has been validated against the codebase and database artifacts. This analysis directly informs V3.0's design decisions — each weakness identified here has a corresponding mitigation in V3.0, and each strength is preserved or extended.

### 2.1 V1.x: The Tactical Foundation (Implemented, Validated)

V1.x encompasses the initial implementation (V1.0), the audit-driven stabilization pass (V1.1), and the feature expansion (V1.2). This is the **production system** — it has been used in real development workflows, and its database contains operational evidence of successful context preservation across multiple projects and extended time periods.

#### 2.1.1 Verified Architecture Strengths

**Genuine Async Pipeline.** V1.x is not merely async-decorated — it implements real concurrent I/O throughout the critical path. The `freeze_logic` function in `bin/pd.py` uses `asyncio.gather` to parallelize Git status capture and terminal state capture simultaneously. Network calls to AI providers use `httpx.AsyncClient` (non-blocking HTTP), and database operations use `aiosqlite` through SQLAlchemy's `AsyncEngine`. The daemon's inactivity loop uses `asyncio.sleep` instead of blocking `time.sleep`. This architecture was achieved through a deliberate refactoring effort (Task 28) that replaced the original blocking `requests` library with `httpx` and converted `subprocess.run` calls to `asyncio.create_subprocess_exec` in `git_utils.py` and `terminal.py`.

**WAL Mode + Foreign Key Pragmas.** The SQLite database is configured with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and foreign key enforcement (`PRAGMA foreign_keys=ON`) via a `connect` event listener in `core/db.py`. This is critical infrastructure: WAL mode allows the daemon and CLI to access the database concurrently without locking, and FK enforcement prevents orphaned snapshots. Both pragmas are set on every new connection, not just at database creation time, ensuring consistency even when the database is accessed by different processes.

**Shell Exit-Code Handshake (Exit 88).** The `pd switch` command does not directly attach to tmux sessions from Python. Instead, the orchestrator returns a `needs_shell_attach` boolean, and `pd.py` exits with status code 88. The shell wrapper function in `shell_integration.zsh` traps this exit code and performs the tmux `attach-session` or `switch-client` at the shell level. This design eliminates the fragile process hierarchy where Python was the parent of the tmux client — if Python crashed, the tmux session would be orphaned. By moving the tmux attachment to the shell, the session management is independent of the Python process lifecycle. This was a deliberate fix (Task 26) addressing a P0 reliability issue identified in the code audit.

**Hydra Configuration with User Override Merging.** Configuration management uses Hydra with structured configs (`SystemConfig` dataclass in `core/config.py`). The `load_config` function composes the base configuration from `prime_directive/conf/config.yaml` and then merges user-specific overrides from `~/.prime-directive/config.yaml`. Environment variables in paths are expanded at load time. This provides a clean separation between application defaults and user preferences, and it supports the `--hq` flag for tiered AI model selection without configuration file edits.

**Budget Enforcement with Full Audit Trail.** The `AIUsageLog` table records every AI provider call with provider name, model, input/output token counts, cost estimate, success status, and associated repository. The `check_budget` function in `core/ai_providers.py` aggregates month-to-date costs before each call and blocks further API usage when the monthly budget is exceeded. This prevents bill shock from OpenAI fallback usage and provides complete cost visibility via `pd ai-usage`.

**Robust Feature Set.** The following features have been implemented, tested, and used in production:

| Feature | Command | Implementation |
|---------|---------|---------------|
| Interactive freeze interview | `pd freeze` | 4-question wizard (objective, blocker, next step, notes) with `--no-interview` bypass |
| Tiered AI models | `pd freeze --hq` | Switches from cheap model (`qwen2.5-coder`) to expensive model (`gpt-4o`) |
| Longitudinal analysis | `pd sitrep --deep-dive` | Compiles last N snapshots into historical narrative, processed by HQ model |
| Time-to-commit metrics | `pd metrics` | Tracks `SWITCH_IN` → `COMMIT` deltas from `EventLog` |
| System diagnostics | `pd doctor` | Checks tmux, editor, Ollama, OpenAI key, DB, config |
| AI cost tracking | `pd ai-usage` | Month-to-date cost breakdown from `AIUsageLog` |
| Git hook integration | `pd install-hooks` | Installs post-commit hook that logs `COMMIT` events |
| Fuzzy repo ID matching | `pd freeze typo-repo` | `difflib.get_close_matches` suggests corrections |
| Auto-freeze on inactivity | `pd-daemon` | Watchdog-based file monitoring with configurable timeout |
| Daemon context awareness | `pd-daemon` | Checks tmux client presence, detects IDE environments |

#### 2.1.2 Verified Architecture Weaknesses

**No Portfolio Awareness.** V1.x treats each repository as an independent entity. It cannot answer cross-project questions: which project is most urgent, which projects block others, or how the developer's time should be allocated. The `config.yaml` stores a flat list of repositories with `id`, `path`, `priority`, and `active_branch` — but `priority` is a static integer that never influences any decision. There is no dependency graph, no strategic weighting, and no concept of project roles or domains.

**Stale Comments in Critical Code.** The `freeze_logic` function in `pd.py` contains the comment `"Blocking Network Call - could be made async with httpx"` on the line immediately before an `await generate_sitrep()` call — the call is already async, and the migration to httpx was completed in Task 28. This kind of stale documentation erodes trust in code comments and can mislead future contributors about the system's actual architecture.

**Sync Holdouts in Daemon/Tmux.** While the core CLI path is fully async, `pd_daemon.py` uses synchronous `subprocess.run` for tmux session checks (`has-session`, `list-clients`), and `core/tmux.py` uses synchronous subprocess calls for all tmux operations (session creation, client switching, detaching). These are blocking calls that could stall the event loop if tmux is slow to respond, though in practice the 2-second timeouts mitigate this.

**Shell Completion is Incomplete.** The `_pd_completion` function in `shell_integration.zsh` only lists `'list' 'status' 'doctor' 'freeze' 'switch'` as completable commands. The commands `sitrep`, `metrics`, `ai-usage`, and `install-hooks` are missing. This is a minor UX gap but representative of the "last mile" polish that V1.x lacks.

**No Composite Index for Latest-Snapshot Queries.** Task 18 (DB integrity improvements) claimed to add a `(repo_id, timestamp)` composite index for optimizing latest-snapshot retrieval. Verification shows that `repo_id` is individually indexed on `ContextSnapshot`, but no composite index exists. For small databases this is irrelevant, but it would matter at scale.

**`chpwd` Hook is a Placeholder.** The `pd_chpwd` function in `shell_integration.zsh` executes `true` (a no-op). The comment explains that invoking Python on every `cd` is too slow, recommending explicit `pd switch` instead. This is a reasonable trade-off, but it means automatic context detection on directory change is not implemented.

### 2.2 V2.1: The Strategic Vision (Proposed, Unimplemented)

V2.1 was documented in `PD-ARCH-V2.1-STRATEGIST_2025-12-16.md` as a design proposal titled "The Grand Strategist Protocol." It describes a portfolio-wide intelligence layer with a new CLI command (`pd overseer`), new configuration files (`empire.yaml`, `strategy.md`), new database tables (`RepositoryHeartbeat`), and a 6-stage scoring/validation pipeline. **None of this was implemented.** No code, no database tables, no configuration files, and no Task Master tasks exist for V2.1. It remains a design document.

#### 2.2.1 Verified Design Strengths

**Algorithm-First, AI-as-Validator.** V2.1's most important design decision is that the core prioritization logic is a deterministic scoring algorithm, not an LLM prompt. The LLM's role is explicitly constrained to validation — it reviews the algorithm's output and provides a "second opinion" on strategic alignment. This makes the system auditable (a developer can predict rankings by reading the algorithm), reproducible (same inputs produce same outputs), and cost-efficient (the expensive LLM call is optional, not required). This directly addresses the "black box" criticism that any LLM-driven system faces.

**Separation of Structure and Strategy.** V2.1 cleanly separates the portfolio's stable structural metadata (`empire.yaml` — projects, roles, dependencies, strategic weights) from the developer's temporal goals (`strategy.md` — "ship MVP by Friday," "don't touch bluethumb"). This is a strong design choice because structural data changes rarely (when you add/remove projects or reorganize dependencies) while strategic goals change frequently (daily or weekly). Mixing them in a single file would create unnecessary churn and merge conflicts.

**Explicit Dependency Graph with Validation.** V2.1 requires all inter-project dependencies to be explicitly declared in `empire.yaml` and mandates cycle detection (via Tarjan's algorithm) and orphan detection on load. This prevents the system from inferring or hallucinating relationships — the dependency graph is 100% developer-authored and machine-validated.

**Cost-Aware Heartbeat Caching.** Instead of invoking the expensive HQ model every time `pd overseer` runs, V2.1 pre-processes tactical state into lightweight "heartbeats" during `pd freeze` using the cheap model. The expensive LLM is only invoked on-demand by `pd overseer`. This dramatically reduces per-freeze cost (heartbeat generation adds minimal overhead to an already-async operation) while ensuring `pd overseer` has fresh tactical context.

**Structured Output Format.** V2.1's proposed output for `pd overseer` is clear and actionable: a ranked list of projects with scores, action directives, and misalignment warnings. This contrasts with the free-text SITREPs of V1.x, which are useful for context but not for decision-making.

#### 2.2.2 Verified Design Weaknesses

**High Configuration Burden.** V2.1 requires the developer to author a detailed `empire.yaml` with domain classifications, role assignments (`RESEARCH`, `INFRASTRUCTURE`, `MAINTENANCE`, `EXPERIMENTAL`), strategic weights (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), and explicit dependency declarations for every project. For a developer with 6+ projects, this is a significant upfront investment that produces zero value until the entire configuration is complete. The design doc acknowledges this ("Progressive Onboarding" is listed as a design principle) but does not specify how progressive onboarding would work in practice.

**No Graceful Degradation.** The 6-stage pipeline assumes all inputs are available: `empire.yaml` exists and is complete, `strategy.md` exists and is current, heartbeats exist for all projects, and the dependency graph is acyclic. The design doc does not specify behavior when any of these conditions are not met. What happens when `empire.yaml` is missing? What if only 2 of 6 projects have heartbeats? What if `strategy.md` hasn't been updated in a month? A production system must handle partial data gracefully.

**No Migration Path from V1.x.** V2.1 introduces `empire.yaml` as a replacement for `config.yaml`'s repository listing, but does not specify how existing V1.x users would migrate. The schema is different — V1.x's `config.yaml` has `{id, path, priority, active_branch}` per repo, while V2.1's `empire.yaml` adds `{domain, role, strategic_weight, description, depends_on}`. There is no migration script, no compatibility layer, and no documentation for the transition.

**Implementation Complexity Gap.** The 6-stage pipeline involves: loading two config files with different formats, querying heartbeats and snapshots from the database, constructing a dependency DAG, computing a multi-factor score, serializing context for an LLM prompt, parsing structured JSON from LLM output, and rendering a formatted report. This is a substantial engineering effort, and the design doc underestimates it by presenting implementation as a handful of bullet-point tasks. No subtask breakdown, no dependency analysis, and no test strategy is provided.

**`strategy.md` is Fragile.** The strategy file is described as "human-readable" natural language with freeform constraints. The LLM must parse this to extract strategic context. This creates a silent failure mode: if the developer writes strategy in a way the LLM doesn't interpret correctly, the overseer's recommendations will be misaligned — and the developer has no way to know this without manually verifying every recommendation against their intent. There is no structured validation for `strategy.md` content.

---

## 3. Synthesized Design Principles

Each principle below is explicitly traced to the strengths it preserves and the weaknesses it mitigates from Section 2. This traceability ensures that V3.0's design decisions are grounded in evidence, not preference.

### 3.1 Extend, Don't Replace

**Preserves:** V1.x's proven async pipeline, database schema, CLI commands, shell integration, Hydra configuration, budget enforcement (§2.1.1).  
**Mitigates:** V2.1's lack of migration path from V1.x (§2.2.2).

V3.0 is implemented as a **layer on top of V1.x**, not a replacement. The existing `config.yaml` continues to define the repository list. The existing `ContextSnapshot`, `EventLog`, and `AIUsageLog` tables are unchanged. The existing CLI commands are unmodified. New functionality is added through:
- A new configuration file (`empire.yaml`) that **references** repositories already defined in `config.yaml` by their `id`.
- A new optional file (`strategy.md`) that is only read by `pd overseer`.
- A new database table (`RepositoryHeartbeat`) that is populated as a side effect of `pd freeze`.
- A new CLI command (`pd overseer`) that consumes all of the above.

This means a V1.x user can upgrade to V3.0 and experience **zero changes** to their existing workflow. The strategic layer activates incrementally as the user creates `empire.yaml` and `strategy.md`.

### 3.2 Algorithm First, AI as Validator

**Preserves:** V2.1's deterministic scoring architecture (§2.2.1).  
**Mitigates:** The "black box" criticism of LLM-driven decision systems.

The core prioritization in `pd overseer` is a **deterministic, auditable scoring algorithm**. Given the same inputs (empire configuration, strategy goals, heartbeat data, dependency graph), the algorithm produces the same ranking every time. The developer can read the scoring formula, understand why Project A ranks above Project B, and override the result if they disagree.

The LLM's role is strictly constrained:
1. **Heartbeat generation** (during `pd freeze`): Summarize the current snapshot into a structured JSON heartbeat using the cheap model. This is a compression task, not a decision task.
2. **Strategic validation** (during `pd overseer`): Review the algorithm's ranked output against the developer's `strategy.md` goals and flag misalignments. The LLM can say "this ranking contradicts your stated goal of shipping by Friday" but it cannot change the ranking.

This separation ensures that the system is useful even without an LLM (the algorithm still produces rankings), and that the LLM's contributions are clearly labeled as advisory.

### 3.3 Progressive Value Delivery

**Preserves:** V1.x's immediate utility without configuration (§2.1.1).  
**Mitigates:** V2.1's high configuration burden and lack of graceful degradation (§2.2.2).

V3.0 delivers value at every level of configuration completeness:

| Configuration Level | What Works |
|---|---|
| **Level 0: No new config** | All V1.x commands work. `pd overseer` prints "No empire.yaml found" with setup instructions. |
| **Level 1: Minimal `empire.yaml`** | `pd overseer` ranks projects using only staleness and recent activity. No roles, no dependencies, no strategy needed. |
| **Level 2: Full `empire.yaml`** | `pd overseer` uses roles, strategic weights, and dependency graph for scoring. Still works without `strategy.md`. |
| **Level 3: Full `empire.yaml` + `strategy.md`** | `pd overseer` adds LLM-powered strategic validation, misalignment detection, and goal-aligned recommendations. |

At each level, the system clearly communicates what additional value would be unlocked by the next level of configuration. The `pd overseer` output includes a "Configuration Health" section that shows which optional inputs are missing and what they would enable.

### 3.4 Structured Over Freeform

**Preserves:** V2.1's explicit dependency graph (§2.2.1) and structured output format (§2.2.1).  
**Mitigates:** V2.1's fragile `strategy.md` parsing (§2.2.2).

Where V2.1 proposed `strategy.md` as fully freeform natural language, V3.0 uses a **semi-structured format**: a YAML frontmatter block with machine-readable fields (deadline, focus project, constraints list) followed by an optional freeform body for nuanced context. This gives the scoring algorithm deterministic inputs (the frontmatter) while still allowing the LLM validator to consider natural language context (the body).

```markdown
---
focus: rna-predict
deadline: 2025-03-14
constraints:
  - Do not deploy black-box changes without staging tests against rna-predict
  - bluethumb is maintenance-only — critical bugs only
---

## Context
The Q1 demo is on Friday. RNA structure prediction accuracy must reach 85%
before the demo. The gradient explosion in the transformer layer is the
primary blocker. Black-box API stability is a prerequisite — any breaking
change would cascade to rna-predict's data pipeline.
```

The frontmatter fields are validated on load (is `focus` a known project ID? is `deadline` a valid date?). Parse failures produce clear error messages, not silent misalignment.

### 3.5 Cost-Aware by Default

**Preserves:** V1.x's budget enforcement and tiered model support (§2.1.1).  
**Mitigates:** Uncontrolled API costs from frequent LLM invocations.

V3.0 introduces two new LLM touchpoints (heartbeat generation, strategic validation) that must not create cost surprises:

- **Heartbeat generation** runs during every `pd freeze`, using the cheap model (`ai_model`, typically `qwen2.5-coder` or `gpt-4o-mini`). The heartbeat prompt is designed to be short (under 500 tokens input, under 200 tokens output). At ~$0.0001 per call, this adds negligible cost to the existing freeze operation.
- **Strategic validation** runs only on explicit `pd overseer` invocation, using the expensive model (`ai_model_hq`, typically `gpt-4o`). The strategic brief prompt is longer (2000–4000 tokens depending on portfolio size) but runs infrequently (a few times per day at most).
- Both touchpoints are subject to the existing `ai_monthly_budget_usd` budget and are logged to `AIUsageLog`.
- If the budget is exceeded, `pd overseer` still produces the deterministic ranking (Stages 1–4) but skips the LLM validation (Stage 5), clearly labeling the output as "unvalidated."

### 3.6 Fail Loud, Degrade Gracefully

**Preserves:** V1.x's resilient fallback behavior (Ollama → OpenAI → fallback SITREP) (§2.1.1).  
**Mitigates:** V2.1's implicit assumption that all inputs are always available (§2.2.2).

Every component in V3.0 has explicit behavior for missing or stale inputs:

| Missing Input | Behavior |
|---|---|
| `empire.yaml` does not exist | `pd overseer` prints setup wizard prompt. All V1.x commands unaffected. |
| `strategy.md` does not exist | Scoring works without strategic context. Output notes "No strategy file — recommendations are based on structural data only." |
| Heartbeat missing for a project | Scoring uses last `ContextSnapshot` timestamp as a staleness proxy. Output notes "No heartbeat for [project] — using snapshot age as fallback." |
| Heartbeat is stale (>24h old) | Staleness factor increases the project's urgency score. Output flags "Stale heartbeat — last freeze was X hours ago." |
| LLM unavailable / budget exceeded | Stages 1–4 produce ranking. Stage 5 (LLM validation) is skipped. Output labeled "Deterministic ranking only — LLM validation unavailable." |
| Dependency cycle detected | `pd overseer` refuses to run and prints the cycle with remediation instructions. |
| `strategy.md` frontmatter parse error | `pd overseer` prints the specific parse error and line number. Falls back to scoring without strategic context. |

All degradation is **explicit** — the output always tells the developer what data was missing and how it affected the result.

### 3.7 Testable at Every Layer

**Preserves:** V1.x's comprehensive test suite (81+ tests across CLI, freeze, switch, daemon, DB, git parsing) (§2.1.1).  
**Mitigates:** V2.1's lack of test strategy (§2.2.2).

V3.0 is designed for testability:
- The scoring algorithm is a pure function: given inputs (empire config, heartbeats, dependency graph, strategy goals), it produces a ranked list. No side effects, no I/O, no LLM calls. This function can be exhaustively unit-tested with deterministic inputs and expected outputs.
- The heartbeat generator is tested independently of `pd freeze`, using mock snapshots.
- The LLM validator is tested using recorded prompt/response pairs, with assertions on the structured JSON output format.
- The `empire.yaml` and `strategy.md` parsers are tested with valid, invalid, partial, and adversarial inputs.
- Integration tests run `pd overseer` in `mock_mode` (existing V1.x infrastructure) to verify the full pipeline without real LLM calls.
- The dependency graph validator (cycle detection, orphan detection) is tested with known cyclic and acyclic graphs.

---

## 4. Architecture Overview

### 4.1 Layered Architecture

V3.0 extends V1.x's existing architecture with two new layers (3 and 4) while leaving the foundational layers (1 and 2) unchanged. Each layer has a clear responsibility boundary, and higher layers depend only on lower layers — never the reverse.

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4: Orchestration & Synthesis                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  pd overseer — The Grand Strategist Engine                 │  │
│  │  • 6-stage deterministic scoring pipeline                  │  │
│  │  • LLM strategic validation (optional, budget-gated)       │  │
│  │  • Formatted directive output with misalignment detection  │  │
│  └────────────────────────────────────────────────────────────┘  │
│  New in V3.0                                                     │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: Portfolio Intelligence                                 │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐  │
│  │  Empire Registry  │ │  Strategy Parser │ │  Heartbeat Mgr  │  │
│  │  (empire.yaml)    │ │  (strategy.md)   │ │  (DB + LLM)     │  │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘  │
│  ┌──────────────────┐ ┌──────────────────────────────────────┐  │
│  │  Dependency Graph │ │  Scoring Algorithm                   │  │
│  │  (DAG + Tarjan)   │ │  (deterministic, pure function)      │  │
│  └──────────────────┘ └──────────────────────────────────────┘  │
│  New in V3.0                                                     │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: Tactical Operations (V1.x — UNCHANGED)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ pd freeze│ │ pd switch│ │ pd sitrep│ │ pd metrics/doctor │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ Scribe   │ │Orchestrtr│ │ AI Provdr│ │ Budget Enforcer   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  Existing V1.x — no modifications                               │
├──────────────────────────────────────────────────────────────────┤
│  Layer 1: Foundation (V1.x — UNCHANGED)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ SQLite   │ │ Hydra    │ │ httpx    │ │ asyncio runtime   │  │
│  │ +aiosql  │ │ Config   │ │ Async    │ │ + event loop      │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ Git Utils│ │ Terminal │ │ Tmux Mgr │ │ Shell Integration  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│  Existing V1.x — no modifications                               │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Inventory

The following table lists every component in V3.0, indicating whether it is existing (from V1.x), modified, or new.

| Component | File | Status | Layer | Description |
|-----------|------|--------|-------|-------------|
| CLI entry point | `bin/pd.py` | **Modified** | 2→4 | Adds `pd overseer` command. All existing commands unchanged. |
| Empire Registry | `core/empire.py` | **New** | 3 | Parses and validates `empire.yaml`. Provides typed `EmpireConfig` object. |
| Strategy Parser | `core/strategy.py` | **New** | 3 | Parses `strategy.md` frontmatter + body. Returns `StrategyContext` object. |
| Heartbeat Manager | `core/heartbeat.py` | **New** | 3 | Generates heartbeats during `pd freeze`. Queries heartbeats for `pd overseer`. |
| Dependency Graph | `core/graph.py` | **New** | 3 | Builds DAG from `empire.yaml` `depends_on` fields. Cycle/orphan detection. |
| Scoring Algorithm | `core/scoring.py` | **New** | 3 | Pure function: inputs → ranked project list with scores. |
| Overseer Pipeline | `core/overseer.py` | **New** | 4 | Orchestrates the 6-stage pipeline. Calls scoring, LLM validator, renderer. |
| LLM Validator | `core/validator.py` | **New** | 4 | Constructs strategic brief, calls HQ model, parses structured response. |
| Overseer Renderer | `core/renderer.py` | **New** | 4 | Formats the overseer report for terminal output using Rich. |
| DB Schema | `core/db.py` | **Modified** | 1 | Adds `RepositoryHeartbeat` table. All existing tables unchanged. |
| Config Schema | `core/config.py` | **Modified** | 1 | Adds `EmpireConfig` and `StrategyConfig` dataclasses. Existing configs unchanged. |
| Freeze Logic | `bin/pd.py` | **Modified** | 2 | After existing freeze completes, generates heartbeat as async side effect. |
| Scribe | `core/scribe.py` | Unchanged | 2 | Existing SITREP generation. Not modified. |
| Orchestrator | `core/orchestrator.py` | Unchanged | 2 | Existing switch logic. Not modified. |
| AI Providers | `core/ai_providers.py` | Unchanged | 2 | Existing Ollama/OpenAI providers. Reused by heartbeat and validator. |
| Shell Integration | `system/shell_integration.zsh` | **Modified** | 1 | Adds `overseer` to shell completion list. |

### 4.3 Data Flow Overview

The following diagram shows how data flows through V3.0 during the two primary operations: `pd freeze` (which now generates heartbeats) and `pd overseer` (which consumes everything).

```
pd freeze <repo_id>
│
├── [Existing V1.x] ─────────────────────────────┐
│   ├── asyncio.gather(git_status, terminal_state)│
│   ├── generate_sitrep (cheap model)             │
│   ├── save ContextSnapshot to DB                │
│   └── log EventLog, AIUsageLog                  │
│                                                  │
├── [New V3.0] ───────────────────────────────────┐
│   ├── generate_heartbeat (cheap model)          │
│   │   Input: ContextSnapshot just saved         │
│   │   Output: structured JSON heartbeat         │
│   ├── save RepositoryHeartbeat to DB            │
│   └── log AIUsageLog for heartbeat call         │
│                                                  │
└── Done. Total added latency: ~200ms (async)


pd overseer
│
├── Stage 1: Load Context ────────────────────────┐
│   ├── Read empire.yaml → EmpireConfig           │
│   ├── Read strategy.md → StrategyContext         │
│   ├── Query RepositoryHeartbeat for each project │
│   └── Query ContextSnapshot (fallback if no HB)  │
│                                                   │
├── Stage 2: Build Dependency Graph ──────────────┐
│   ├── Construct DAG from depends_on fields       │
│   ├── Run Tarjan's algorithm (cycle detection)   │
│   └── Compute topological order                  │
│                                                   │
├── Stage 3: Compute Scores ──────────────────────┐
│   ├── For each project: compute multi-factor     │
│   │   score (staleness, weight, role, deps,      │
│   │   blocker status, strategy focus)            │
│   └── Sort projects by score (descending)        │
│                                                   │
├── Stage 4: Classify & Label ────────────────────┐
│   ├── Assign action categories:                  │
│   │   CRITICAL / MONITOR / DEPRIORITIZE          │
│   └── Generate action directive per project      │
│                                                   │
├── Stage 5: LLM Validation (optional) ───────────┐
│   ├── Construct strategic brief (JSON)           │
│   ├── Call ai_model_hq                           │
│   ├── Parse structured response                  │
│   └── Merge misalignment warnings into output    │
│                                                   │
├── Stage 6: Render Report ───────────────────────┐
│   ├── Format with Rich (colors, tables, emojis) │
│   ├── Include configuration health section       │
│   └── Print to terminal                          │
│                                                   │
└── Done. Total time: ~2-5s (with LLM), <1s (without)
```

### 4.4 File System Layout

V3.0 introduces new files in two locations: the application package (for code) and the user's home directory (for configuration).

**Application package** (`prime_directive/`):
```
prime_directive/
├── bin/
│   ├── pd.py              # Modified: adds pd overseer command
│   └── pd_daemon.py       # Unchanged
├── conf/
│   └── config.yaml        # Unchanged
├── core/
│   ├── ai_providers.py    # Unchanged (reused by heartbeat/validator)
│   ├── auto_installer.py  # Unchanged
│   ├── config.py          # Modified: adds EmpireConfig, StrategyConfig
│   ├── db.py              # Modified: adds RepositoryHeartbeat table
│   ├── dependencies.py    # Unchanged
│   ├── empire.py          # NEW: empire.yaml parser
│   ├── git_utils.py       # Unchanged
│   ├── graph.py           # NEW: dependency DAG + cycle detection
│   ├── heartbeat.py       # NEW: heartbeat generation + querying
│   ├── logging_utils.py   # Unchanged
│   ├── orchestrator.py    # Unchanged
│   ├── overseer.py        # NEW: 6-stage pipeline orchestration
│   ├── renderer.py        # NEW: Rich-formatted overseer output
│   ├── scoring.py         # NEW: deterministic scoring algorithm
│   ├── scribe.py          # Unchanged
│   ├── strategy.py        # NEW: strategy.md parser
│   ├── tasks.py           # Unchanged
│   ├── terminal.py        # Unchanged
│   ├── tmux.py            # Unchanged
│   ├── validator.py       # NEW: LLM strategic validation
│   └── windsurf.py        # Unchanged
└── system/
    └── shell_integration.zsh  # Modified: updated completion list
```

**User configuration** (`~/.prime-directive/`):
```
~/.prime-directive/
├── config.yaml            # Existing V1.x user overrides (unchanged)
├── empire.yaml            # NEW: portfolio structure definition
├── strategy.md            # NEW: temporal strategic goals
└── data/
    └── prime.db           # Existing DB, now with RepositoryHeartbeat table
```

---

## 5. Data Model

This section defines the schema for every data structure in V3.0: the new configuration files (`empire.yaml`, `strategy.md`), the new database table (`RepositoryHeartbeat`), and the structured types that flow between pipeline stages. Existing V1.x schemas (`ContextSnapshot`, `EventLog`, `AIUsageLog`, `Repository`) are unchanged and documented in `core/db.py`.

### 5.1 Empire Registry (`empire.yaml`)

The empire registry defines the **stable structural metadata** of the developer's project portfolio. It changes infrequently — only when projects are added, removed, or reorganized. It lives at `~/.prime-directive/empire.yaml`.

**Design rationale:** V2.1 proposed `empire.yaml` as a replacement for `config.yaml`'s repository listing. V3.0 instead makes `empire.yaml` an **overlay** that references repositories already defined in `config.yaml` by their `id`. This means:
- V1.x's `config.yaml` remains the single source of truth for `{id, path, priority, active_branch}`.
- `empire.yaml` adds strategic metadata (`domain`, `role`, `strategic_weight`, `description`, `depends_on`) for projects that opt into portfolio management.
- Projects listed in `config.yaml` but absent from `empire.yaml` are still tracked by V1.x commands but excluded from `pd overseer` scoring.
- Projects listed in `empire.yaml` but absent from `config.yaml` produce a validation error on load.

#### 5.1.1 Full Schema

```yaml
# ~/.prime-directive/empire.yaml
# Portfolio structure definition for Prime Directive V3.0 Grand Strategist
# All project IDs must match entries in config.yaml repos section

version: "3.0"

projects:
  rna-predict:
    # domain: Logical grouping for the project. Used for display and optional
    # domain-level aggregation in scoring. Freeform string.
    domain: "research"

    # role: The project's functional role in the portfolio.
    # Affects scoring weights — RESEARCH and INFRASTRUCTURE score higher
    # than MAINTENANCE under default weights.
    # Enum: RESEARCH | INFRASTRUCTURE | MAINTENANCE | EXPERIMENTAL
    role: "RESEARCH"

    # strategic_weight: How important this project is to the portfolio's
    # overall success. Directly multiplies the base score.
    # Enum: CRITICAL | HIGH | MEDIUM | LOW
    # Numeric equivalents: CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1
    strategic_weight: "CRITICAL"

    # description: Natural language description of the project's purpose.
    # Included in the LLM strategic brief for context. Should be 1-2
    # sentences describing what the project does and why it matters.
    description: >
      Primary model for predicting RNA tertiary structure. Success is the
      company's top priority for Q1. Accuracy must reach 85% for the demo.

    # depends_on: Explicit list of project IDs that this project depends on.
    # Used to build the dependency DAG. If a dependency is blocked, the
    # dependent project's urgency increases. Must not create cycles.
    # Optional — omit or use empty list for projects with no dependencies.
    depends_on:
      - black-box

  black-box:
    domain: "core-infra"
    role: "INFRASTRUCTURE"
    strategic_weight: "HIGH"
    description: >
      Core data pipeline and API service. Provides the data ingestion and
      transformation layer used by rna-predict and bluethumb. API stability
      is paramount.
    depends_on: []

  bluethumb:
    domain: "product"
    role: "MAINTENANCE"
    strategic_weight: "LOW"
    description: >
      Legacy UI for visualizing model outputs. Maintenance mode only —
      no new features, only critical bug fixes.
    depends_on:
      - black-box

  prime-directive:
    domain: "tooling"
    role: "INFRASTRUCTURE"
    strategic_weight: "MEDIUM"
    description: >
      Developer tooling for context preservation and portfolio management.
      Self-referential — this is the tool managing all other projects.
    depends_on: []
```

#### 5.1.2 Validation Rules

The `empire.yaml` parser (`core/empire.py`) enforces the following rules on load:

| Rule | Error Behavior |
|------|---------------|
| `version` field must be present and equal `"3.0"` | Hard error with message. |
| Every project ID in `projects` must exist in `config.yaml`'s `repos` section | Hard error listing unrecognized IDs. |
| `role` must be one of `RESEARCH`, `INFRASTRUCTURE`, `MAINTENANCE`, `EXPERIMENTAL` | Hard error with valid options listed. |
| `strategic_weight` must be one of `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` | Hard error with valid options listed. |
| `depends_on` entries must reference project IDs defined in this same `empire.yaml` | Hard error listing invalid references. |
| The dependency graph must be acyclic (validated via Tarjan's algorithm) | Hard error printing the cycle path. |
| `description` must be a non-empty string | Warning (scoring works without it, but LLM validation is degraded). |

#### 5.1.3 Typed Representation

```python
# core/empire.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class ProjectRole(str, Enum):
    RESEARCH = "RESEARCH"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    MAINTENANCE = "MAINTENANCE"
    EXPERIMENTAL = "EXPERIMENTAL"

class StrategicWeight(str, Enum):
    CRITICAL = "CRITICAL"   # Numeric: 4
    HIGH = "HIGH"           # Numeric: 3
    MEDIUM = "MEDIUM"       # Numeric: 2
    LOW = "LOW"             # Numeric: 1

@dataclass
class EmpireProject:
    id: str
    domain: str
    role: ProjectRole
    strategic_weight: StrategicWeight
    description: str
    depends_on: list[str] = field(default_factory=list)

    @property
    def weight_numeric(self) -> int:
        return {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}[
            self.strategic_weight.value
        ]

@dataclass
class EmpireConfig:
    version: str
    projects: dict[str, EmpireProject]
```

### 5.2 Strategy File (`strategy.md`)

The strategy file captures the developer's **temporal, high-level goals** — what they're trying to achieve this week, what constraints apply, and what the deadline is. It changes frequently (daily or weekly) and is written by the developer in a semi-structured format.

**Design rationale:** V2.1 proposed `strategy.md` as fully freeform natural language. V3.0 adds a YAML frontmatter block with machine-readable fields that the scoring algorithm can consume deterministically, while preserving the freeform body for LLM context. This addresses the "fragile parsing" weakness identified in §2.2.2.

#### 5.2.1 Full Format

```markdown
---
# Required: Which project should receive the most attention right now?
# Must be a valid project ID from empire.yaml.
focus: rna-predict

# Optional: Hard deadline for the current strategic goal.
# ISO 8601 date format. Used by scoring to boost urgency as deadline approaches.
deadline: 2025-03-14

# Optional: Explicit constraints that the LLM validator should enforce.
# Each constraint is a natural language string. The scoring algorithm does
# not parse these — they are passed to the LLM for validation only.
constraints:
  - Do not deploy black-box changes without staging tests against rna-predict
  - bluethumb is maintenance-only — critical bugs only
  - Prioritize accuracy improvements over speed optimizations in rna-predict
---

## Context

The Q1 demo is on Friday. RNA structure prediction accuracy must reach 85%
before the demo. The gradient explosion in the transformer layer is the
primary blocker — we've tried learning rate warmup and gradient clipping
without success.

Black-box API stability is a prerequisite — any breaking change would
cascade to rna-predict's data pipeline. The v2.3 API migration is in
progress but must not be deployed until rna-predict's staging branch
passes all integration tests.

## Notes

- Last week's attempt at mixed-precision training caused numerical
  instability. Reverting to FP32 for now.
- The demo environment needs GPU access — coordinate with infra team.
```

#### 5.2.2 Frontmatter Validation Rules

| Field | Required | Validation |
|-------|----------|------------|
| `focus` | Yes | Must be a valid project ID in `empire.yaml`. |
| `deadline` | No | Must be a valid ISO 8601 date (YYYY-MM-DD). Must be in the future (warning if past). |
| `constraints` | No | Must be a list of strings. No structural validation on content (consumed by LLM). |

If the frontmatter is malformed or missing, `pd overseer` falls back to scoring without strategic context and displays a clear warning.

#### 5.2.3 Typed Representation

```python
# core/strategy.py
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

@dataclass
class StrategyContext:
    focus: str                              # Project ID to prioritize
    deadline: Optional[date] = None         # Hard deadline for current goal
    constraints: list[str] = field(         # LLM-consumed constraints
        default_factory=list
    )
    body: str = ""                          # Freeform markdown body for LLM context
    source_path: str = ""                   # Path to strategy.md for error reporting

    @property
    def days_until_deadline(self) -> Optional[int]:
        if self.deadline is None:
            return None
        return (self.deadline - date.today()).days
```

### 5.3 Repository Heartbeat (Database Table)

Heartbeats are lightweight, structured summaries of a project's tactical state, generated during `pd freeze` using the cheap AI model. They serve as a **cache layer** between raw `ContextSnapshot` data and the `pd overseer` scoring pipeline — instead of the overseer having to process full snapshots, it reads pre-digested heartbeats.

**Design rationale:** V2.1 proposed heartbeats as a cost-optimization measure, and V3.0 preserves this design. The key insight is that `pd freeze` already calls the AI provider to generate a SITREP — generating a heartbeat is an additional call that runs concurrently (via `asyncio.gather`) with negligible latency impact.

#### 5.3.1 Database Schema

```python
# Addition to core/db.py

class HeartbeatStatus(str, Enum):
    """Tactical status derived from snapshot analysis."""
    ACTIVE = "ACTIVE"           # Developer is actively working
    BLOCKED = "BLOCKED"         # Explicit blocker identified
    IDLE = "IDLE"               # No recent activity
    COMPLETED = "COMPLETED"     # Recent milestone or task completion

class RepositoryHeartbeat(SQLModel, table=True):  # type: ignore[call-arg]
    """Lightweight tactical summary generated during pd freeze."""

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: str = Field(foreign_key="repository.id", index=True)
    snapshot_id: int = Field(
        foreign_key="contextsnapshot.id"
    )  # Links to the snapshot that generated this heartbeat
    timestamp: datetime = Field(default_factory=_utcnow, index=True)

    # Structured fields extracted by cheap LLM from snapshot
    status: HeartbeatStatus = Field(index=True)
    summary: str             # 1-2 sentence tactical summary
    blocker: Optional[str] = Field(default=None)   # Primary blocker if status=BLOCKED
    eta_minutes: Optional[int] = Field(default=None)  # Estimated time to next milestone
    confidence: float = Field(default=0.5)  # LLM's self-assessed confidence (0-1)

    # Raw JSON from LLM response (for debugging/auditing)
    raw_json: Optional[str] = Field(default=None)
```

#### 5.3.2 Heartbeat JSON Schema (LLM Output)

The cheap model is prompted to produce a JSON object matching this schema:

```json
{
  "status": "BLOCKED",
  "summary": "Gradient explosion in transformer layer. Learning rate warmup and gradient clipping both failed.",
  "blocker": "Gradient explosion causing NaN losses after 50 training steps",
  "eta_minutes": null,
  "confidence": 0.8
}
```

The parser validates the JSON structure and falls back to `HeartbeatStatus.IDLE` with a generic summary if the LLM response is malformed.

#### 5.3.3 Staleness Calculation

Heartbeat staleness is a key input to the scoring algorithm. The staleness function considers:

```python
def compute_staleness(heartbeat: Optional[RepositoryHeartbeat],
                      fallback_snapshot: Optional[ContextSnapshot],
                      now: datetime) -> float:
    """
    Compute a staleness score (0.0 = fresh, 1.0 = maximally stale).

    Uses heartbeat timestamp if available, falls back to latest
    ContextSnapshot timestamp, and returns 1.0 if neither exists.
    """
    if heartbeat is not None:
        age_hours = (now - heartbeat.timestamp).total_seconds() / 3600
    elif fallback_snapshot is not None:
        age_hours = (now - fallback_snapshot.timestamp).total_seconds() / 3600
    else:
        return 1.0  # No data at all — maximally stale

    # Sigmoid-like curve: 0h=0.0, 4h=0.2, 12h=0.5, 24h=0.8, 48h+=0.95
    return min(1.0, age_hours / (age_hours + 12.0))
```

### 5.4 Scoring Input Types

The scoring algorithm operates on structured types, not raw database rows. These types are assembled in Stage 1 of the pipeline and consumed in Stage 3.

```python
# core/scoring.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProjectState:
    """Assembled state for a single project, ready for scoring."""
    project: EmpireProject               # From empire.yaml
    heartbeat: Optional[RepositoryHeartbeat]  # Latest heartbeat (may be None)
    latest_snapshot: Optional[ContextSnapshot]  # Latest snapshot (fallback)
    staleness: float                     # 0.0 (fresh) to 1.0 (stale)
    is_focus: bool                       # True if this is strategy.md's focus project
    days_until_deadline: Optional[int]   # From strategy.md (None if no deadline)
    dependency_depth: int                # Depth in topological order (0 = leaf)
    has_blocked_dependent: bool          # True if another project depends on this and is BLOCKED
    blocker_text: Optional[str]          # From heartbeat, if status=BLOCKED

@dataclass
class ScoredProject:
    """Scoring output for a single project."""
    project_id: str
    score: float                         # 0.0–10.0
    rank: int                            # 1-based rank
    category: str                        # "CRITICAL" | "MONITOR" | "DEPRIORITIZE"
    action_directive: str                # 1-sentence recommended action
    score_breakdown: dict[str, float]    # Factor-by-factor breakdown for transparency
    warnings: list[str]                  # Staleness warnings, missing data notices, etc.
```

### 5.5 Existing V1.x Schema (Unchanged — Reference)

For completeness, the existing database tables that V3.0 reads but does not modify:

| Table | Key Fields | Used By V3.0 |
|-------|-----------|--------------|
| `Repository` | `id`, `path`, `priority`, `active_branch`, `last_snapshot_id` | Validated against `empire.yaml` project IDs |
| `ContextSnapshot` | `repo_id`, `timestamp`, `git_status_summary`, `ai_sitrep`, `human_objective`, `human_blocker`, `human_next_step` | Fallback when no heartbeat exists; `human_blocker` used to infer BLOCKED status |
| `EventLog` | `repo_id`, `event_type`, `timestamp` | Not directly used by `pd overseer` (consumed by `pd metrics` only) |
| `AIUsageLog` | `provider`, `model`, `input_tokens`, `output_tokens`, `cost_estimate_usd` | Budget checks for heartbeat generation and LLM validation |

---

## 6. The `pd overseer` Pipeline

The `pd overseer` command executes a deterministic, 6-stage pipeline. Stages 1–4 are **pure computation** with no external dependencies (no LLM, no network). Stage 5 is an **optional LLM call** that enriches the output. Stage 6 is **rendering**. This design ensures the command is useful even when offline or over budget.

### 6.1 Stage 1: Load Context

**Purpose:** Gather all inputs needed for scoring into typed, validated structures.

**Inputs:**
- `~/.prime-directive/empire.yaml` → `EmpireConfig`
- `~/.prime-directive/strategy.md` → `StrategyContext` (optional)
- `RepositoryHeartbeat` table → latest heartbeat per project
- `ContextSnapshot` table → latest snapshot per project (fallback)
- `config.yaml` → repo list (for cross-validation)

**Algorithm:**

```python
async def load_context(cfg: DictConfig) -> PipelineContext:
    # 1. Load and validate empire.yaml
    empire_path = os.path.expanduser("~/.prime-directive/empire.yaml")
    if not os.path.exists(empire_path):
        raise EmpireNotFoundError(empire_path)
    empire = parse_empire(empire_path, cfg.repos)  # Cross-validates against config.yaml

    # 2. Load strategy.md (optional)
    strategy_path = os.path.expanduser("~/.prime-directive/strategy.md")
    strategy = None
    if os.path.exists(strategy_path):
        strategy = parse_strategy(strategy_path, empire)  # Validates focus project ID

    # 3. Query latest heartbeats and snapshots from DB
    await init_db(cfg.system.db_path)
    heartbeats = {}   # repo_id -> RepositoryHeartbeat
    snapshots = {}    # repo_id -> ContextSnapshot
    async with get_session(cfg.system.db_path) as session:
        for project_id in empire.projects:
            heartbeats[project_id] = await get_latest_heartbeat(session, project_id)
            snapshots[project_id] = await get_latest_snapshot(session, project_id)

    # 4. Assemble ProjectState for each project
    now = datetime.now(timezone.utc)
    states = {}
    for pid, project in empire.projects.items():
        hb = heartbeats.get(pid)
        snap = snapshots.get(pid)
        states[pid] = ProjectState(
            project=project,
            heartbeat=hb,
            latest_snapshot=snap,
            staleness=compute_staleness(hb, snap, now),
            is_focus=(strategy is not None and strategy.focus == pid),
            days_until_deadline=(
                strategy.days_until_deadline if strategy else None
            ),
            dependency_depth=0,        # Computed in Stage 2
            has_blocked_dependent=False,  # Computed in Stage 2
            blocker_text=(hb.blocker if hb and hb.status == HeartbeatStatus.BLOCKED else None),
        )

    return PipelineContext(empire=empire, strategy=strategy, states=states)
```

**Degradation behavior:**
- If `empire.yaml` is missing: print setup instructions and exit (no scoring possible without project definitions).
- If `strategy.md` is missing: continue without strategic context. `is_focus` is False for all projects, `days_until_deadline` is None.
- If a project has no heartbeat and no snapshot: `staleness = 1.0`, `blocker_text = None`.

### 6.2 Stage 2: Build Dependency Graph

**Purpose:** Construct a directed acyclic graph (DAG) from the `depends_on` declarations in `empire.yaml`, detect cycles, compute topological order, and enrich `ProjectState` with graph-derived properties.

**Algorithm:**

```python
def build_dependency_graph(empire: EmpireConfig, states: dict[str, ProjectState]) -> DAG:
    # 1. Build adjacency list
    # Edge direction: A depends_on B means edge B → A
    # (B must be stable before A can proceed)
    graph = {pid: [] for pid in empire.projects}
    for pid, project in empire.projects.items():
        for dep_id in project.depends_on:
            graph[dep_id].append(pid)  # dep_id is depended upon by pid

    # 2. Cycle detection using Tarjan's algorithm
    sccs = tarjan_scc(graph)
    cycles = [scc for scc in sccs if len(scc) > 1]
    if cycles:
        raise DependencyCycleError(cycles)

    # 3. Compute topological order and depth
    topo_order = topological_sort(graph)
    depth = {}
    for pid in topo_order:
        if not empire.projects[pid].depends_on:
            depth[pid] = 0
        else:
            depth[pid] = max(depth[dep] for dep in empire.projects[pid].depends_on) + 1

    # 4. Enrich ProjectState with graph properties
    for pid, state in states.items():
        state.dependency_depth = depth.get(pid, 0)

        # Check if any project that depends on this one is BLOCKED
        dependents = graph.get(pid, [])
        state.has_blocked_dependent = any(
            states[dep_pid].blocker_text is not None
            for dep_pid in dependents
            if dep_pid in states
        )

    return DAG(graph=graph, topo_order=topo_order, depth=depth)
```

**Tarjan's SCC implementation notes:**
- Standard O(V+E) algorithm. For typical portfolios (5–15 projects), this runs in microseconds.
- Self-loops (project depends on itself) are detected as single-node SCCs and reported as errors.
- Orphan detection: projects in `empire.yaml` that are not referenced by any `depends_on` and have no `depends_on` themselves are flagged as "isolated" in the output (warning, not error).

### 6.3 Stage 3: Compute Scores

**Purpose:** Apply the deterministic scoring algorithm to produce a ranked list of projects.

**The scoring formula** is the core intellectual property of `pd overseer`. It is a weighted sum of factors, each normalized to [0, 1] and multiplied by a configurable weight. The total is scaled to [0, 10].

#### 6.3.1 Scoring Factors

| Factor | Symbol | Range | Description | Default Weight |
|--------|--------|-------|-------------|---------------|
| Strategic Weight | `W_s` | 0.25–1.0 | From `empire.yaml`: CRITICAL=1.0, HIGH=0.75, MEDIUM=0.5, LOW=0.25 | 3.0 |
| Staleness | `W_st` | 0.0–1.0 | From `compute_staleness()`: higher = needs attention sooner | 2.0 |
| Focus Bonus | `W_f` | 0.0 or 1.0 | 1.0 if this is `strategy.md`'s focus project, else 0.0 | 2.5 |
| Deadline Urgency | `W_d` | 0.0–1.0 | `1.0 - (days_until_deadline / 14)`, clamped to [0, 1]. 0.0 if no deadline. | 1.5 |
| Blocker Status | `W_b` | 0.0 or 1.0 | 1.0 if heartbeat status is BLOCKED | 1.0 |
| Dependency Pressure | `W_dep` | 0.0 or 1.0 | 1.0 if a dependent project is BLOCKED (this project is blocking others) | 1.5 |
| Role Weight | `W_r` | 0.25–1.0 | RESEARCH=1.0, INFRASTRUCTURE=0.75, EXPERIMENTAL=0.5, MAINTENANCE=0.25 | 0.5 |

#### 6.3.2 The Formula

```python
def compute_score(state: ProjectState, weights: ScoringWeights) -> float:
    """
    Compute a priority score for a project.

    Returns a float in [0, 10] where higher = more urgent/important.
    The formula is a weighted sum of normalized factors.
    """
    factors = {
        "strategic_weight": _normalize_weight(state.project.strategic_weight),
        "staleness": state.staleness,
        "focus_bonus": 1.0 if state.is_focus else 0.0,
        "deadline_urgency": _deadline_urgency(state.days_until_deadline),
        "blocker_status": 1.0 if state.blocker_text is not None else 0.0,
        "dependency_pressure": 1.0 if state.has_blocked_dependent else 0.0,
        "role_weight": _normalize_role(state.project.role),
    }

    raw = sum(
        factors[k] * getattr(weights, k)
        for k in factors
    )

    # Normalize to [0, 10]
    max_possible = sum(getattr(weights, k) for k in factors)
    score = (raw / max_possible) * 10.0

    return round(score, 1)


def _normalize_weight(w: StrategicWeight) -> float:
    return {"CRITICAL": 1.0, "HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.25}[w.value]

def _normalize_role(r: ProjectRole) -> float:
    return {"RESEARCH": 1.0, "INFRASTRUCTURE": 0.75,
            "EXPERIMENTAL": 0.5, "MAINTENANCE": 0.25}[r.value]

def _deadline_urgency(days: Optional[int]) -> float:
    if days is None:
        return 0.0
    if days <= 0:
        return 1.0  # Past deadline — maximum urgency
    return max(0.0, 1.0 - (days / 14.0))
```

#### 6.3.3 Scoring Weights Configuration

The default weights are embedded in `core/scoring.py` but can be overridden via Hydra configuration in `config.yaml`:

```yaml
# In ~/.prime-directive/config.yaml (optional overrides)
overseer:
  scoring_weights:
    strategic_weight: 3.0
    staleness: 2.0
    focus_bonus: 2.5
    deadline_urgency: 1.5
    blocker_status: 1.0
    dependency_pressure: 1.5
    role_weight: 0.5
```

This allows the developer to tune the algorithm to their preferences. For example, a developer who doesn't use deadlines can set `deadline_urgency: 0.0` to effectively disable that factor.

#### 6.3.4 Score Transparency

Every `ScoredProject` includes a `score_breakdown` dict showing the contribution of each factor. This is critical for auditability — the developer can see exactly why a project scored 9.6 vs 5.2:

```
[rna-predict] Score: 9.6/10
  strategic_weight:    3.0/3.0  (CRITICAL)
  staleness:           1.6/2.0  (last freeze 18h ago)
  focus_bonus:         2.5/2.5  (strategy focus)
  deadline_urgency:    1.3/1.5  (4 days until deadline)
  blocker_status:      1.0/1.0  (BLOCKED: gradient explosion)
  dependency_pressure: 0.0/1.5  (no blocked dependents)
  role_weight:         0.5/0.5  (RESEARCH)
```

### 6.4 Stage 4: Classify & Label

**Purpose:** Convert raw scores into human-readable categories and generate action directives.

**Classification thresholds:**

| Score Range | Category | Emoji | Meaning |
|-------------|----------|-------|---------|
| 7.0–10.0 | `CRITICAL` | 🔥 | Requires immediate attention |
| 4.0–6.9 | `MONITOR` | ⚠️ | Keep an eye on, may need action soon |
| 0.0–3.9 | `DEPRIORITIZE` | 💤 | Safe to ignore for now |

**Action directive generation:** Each project gets a 1-sentence action directive based on its state:

```python
def generate_directive(state: ProjectState, category: str) -> str:
    if state.blocker_text and category == "CRITICAL":
        return f"You are blocked on: {state.blocker_text}. This is your top priority."
    if state.is_focus and category == "CRITICAL":
        return "This is your strategic focus. Dedicate your best hours here."
    if state.has_blocked_dependent:
        blocked_by = [pid for pid, s in all_states.items()
                      if state.project.id in s.project.depends_on
                      and s.blocker_text is not None]
        return f"Your work here is blocking {', '.join(blocked_by)}. Prioritize unblocking."
    if category == "MONITOR":
        return "No immediate action needed. Review if staleness increases."
    if category == "DEPRIORITIZE":
        return "Safe to ignore. Only address critical bugs."
    return "Continue current work."
```

### 6.5 Stage 5: LLM Validation (Optional)

**Purpose:** Use the expensive AI model to validate the algorithm's output against the developer's strategic intent and flag misalignments.

**This stage is skipped when:**
- `strategy.md` does not exist (nothing to validate against)
- The AI monthly budget is exceeded
- The LLM is unavailable (Ollama down, OpenAI key missing)
- The user passes `--no-validate` flag

**When skipped:** The output is labeled "Deterministic ranking only" and proceeds to Stage 6.

**When executed:** The LLM validator constructs a "strategic brief" (JSON document containing the ranked projects, their scores, the strategy frontmatter, and the strategy body), sends it to `ai_model_hq`, and parses a structured JSON response. The response format is:

```json
{
  "alignment_assessment": "ALIGNED" | "MISALIGNED" | "PARTIALLY_ALIGNED",
  "misalignments": [
    {
      "project_id": "bluethumb",
      "issue": "Ranked #3 but strategy says maintenance-only. Any work here contradicts stated constraints.",
      "severity": "HIGH"
    }
  ],
  "recommendation": "Focus exclusively on rna-predict today. The gradient explosion blocker is the only thing standing between you and the Friday demo.",
  "confidence": 0.85
}
```

The full LLM prompt engineering is detailed in Section 8.

### 6.6 Stage 6: Render Report

**Purpose:** Format the complete overseer report for terminal output using Rich.

**Output sections (in order):**

1. **Header:** `>>> THE OVERSEER REPORT <<<` with timestamp
2. **Strategic Focus** (if `strategy.md` exists): Focus project, deadline, days remaining
3. **Misalignment Warning** (if Stage 5 detected issues): Red banner with specific issues
4. **Ranked Project List:** Each project with score, category emoji, action directive, and score breakdown (collapsible via `--verbose`)
5. **LLM Recommendation** (if Stage 5 ran): Strategic validation summary
6. **Configuration Health:** What inputs are present/missing and what they enable
7. **Cost Footer:** Tokens used and cost for this invocation

The renderer uses Rich's `Console`, `Table`, `Panel`, and `Text` objects for formatting, consistent with V1.x's existing Rich usage throughout the CLI.

---

## 7. Integration with V1.x

V3.0's most critical architectural decision is that it **extends** V1.x rather than replacing it. This section details every integration point — where V3.0 code touches V1.x code, what changes are required, and what remains untouched.

### 7.1 Heartbeat Generation in `pd freeze`

The primary integration point is the `freeze_logic` function in `bin/pd.py`. After the existing V1.x freeze completes (snapshot saved, SITREP generated), V3.0 adds a heartbeat generation step as an async side effect.

**Current V1.x flow (unchanged):**
```
freeze_logic():
  1. asyncio.gather(git_status, terminal_state)
  2. generate_sitrep() → ai_sitrep
  3. Save ContextSnapshot to DB
  4. Update Repository.last_snapshot_id
  5. Log AIUsageLog for SITREP call
```

**V3.0 extended flow:**
```
freeze_logic():
  1–5. [Existing V1.x — no changes]
  6. IF empire.yaml exists:
       a. generate_heartbeat(snapshot) → RepositoryHeartbeat JSON
       b. Save RepositoryHeartbeat to DB (linked to snapshot_id)
       c. Log AIUsageLog for heartbeat call
     ELSE:
       Skip silently (V1.x-only mode)
```

**Key implementation details:**

- **Heartbeat generation is fire-and-forget.** If it fails (LLM timeout, budget exceeded, malformed response), the freeze still succeeds. The heartbeat failure is logged as a warning, not an error. The snapshot is already saved by the time heartbeat generation starts.
- **Heartbeat generation uses the cheap model.** It calls the same `ai_providers` infrastructure as SITREP generation, using `cfg.system.ai_model` (not `ai_model_hq`). The prompt is shorter and cheaper than the SITREP prompt.
- **Empire check is a file existence check.** `freeze_logic` does not parse `empire.yaml` — it only checks if the file exists at `~/.prime-directive/empire.yaml`. If absent, the heartbeat step is skipped entirely with zero overhead. This means V1.x users who never create `empire.yaml` experience no change in behavior or performance.
- **The heartbeat is generated from the snapshot, not from raw data.** The heartbeat prompt receives the `ContextSnapshot` fields (git status summary, terminal output, SITREP, human notes) as input, not the raw git/terminal data. This means the heartbeat is a structured compression of an already-compressed snapshot, keeping the prompt short.

**Modification to `bin/pd.py`:**

```python
# After existing freeze_logic saves the snapshot (approximately line 300)

# V3.0: Generate heartbeat if empire.yaml exists
empire_path = os.path.expanduser("~/.prime-directive/empire.yaml")
if os.path.exists(empire_path):
    try:
        heartbeat = await generate_heartbeat(
            snapshot=snapshot,
            repo_id=repo_id,
            model=config.system.ai_model,
            provider=config.system.ai_provider,
            api_url=config.system.ollama_api_url,
            timeout_seconds=config.system.ollama_timeout_seconds,
            db_path=config.system.db_path,
            monthly_budget_usd=config.system.ai_monthly_budget_usd,
        )
        if heartbeat:
            async with get_session(config.system.db_path) as session:
                session.add(heartbeat)
                await session.commit()
            logger.info(f"Heartbeat generated for {repo_id}: {heartbeat.status}")
    except Exception as e:
        logger.warning(f"Heartbeat generation failed for {repo_id}: {e}")
        # Do not propagate — freeze already succeeded
```

### 7.2 Database Schema Extension

The `RepositoryHeartbeat` table is added to `core/db.py` alongside the existing `ContextSnapshot`, `EventLog`, and `AIUsageLog` tables. Because V1.x uses SQLModel with `SQLModel.metadata.create_all()` in `init_db`, the new table is created automatically on first database initialization after the V3.0 upgrade. No manual migration is required.

**Important:** The `RepositoryHeartbeat` table has foreign keys to both `Repository` (via `repo_id`) and `ContextSnapshot` (via `snapshot_id`). These are enforced by the existing `PRAGMA foreign_keys=ON` setting. This means:
- A heartbeat cannot reference a non-existent snapshot.
- Deleting a snapshot will cascade-delete its heartbeat (if `ON DELETE CASCADE` is set) or block deletion (if not). V3.0 uses the default SQLModel behavior (no cascade), which means snapshots with heartbeats cannot be deleted without first deleting the heartbeat. This is intentional — heartbeats should never be orphaned.

### 7.3 Configuration Extension

V3.0 adds new structured config dataclasses to `core/config.py`:

```python
# Addition to core/config.py

@dataclass
class ScoringWeightsConfig:
    """Configurable weights for the overseer scoring algorithm."""
    strategic_weight: float = 3.0
    staleness: float = 2.0
    focus_bonus: float = 2.5
    deadline_urgency: float = 1.5
    blocker_status: float = 1.0
    dependency_pressure: float = 1.5
    role_weight: float = 0.5

@dataclass
class OverseerConfig:
    """Configuration for the pd overseer command."""
    scoring_weights: ScoringWeightsConfig = field(
        default_factory=ScoringWeightsConfig
    )
    empire_path: str = "~/.prime-directive/empire.yaml"
    strategy_path: str = "~/.prime-directive/strategy.md"
    validate_with_llm: bool = True  # Can be disabled via --no-validate
    max_heartbeat_age_hours: float = 48.0  # Heartbeats older than this are ignored
```

These are added as an optional `overseer` key in the Hydra config hierarchy. If the key is absent from `config.yaml`, the defaults are used. This maintains full backward compatibility — existing `config.yaml` files without an `overseer` section work without modification.

The corresponding addition to `conf/config.yaml` (default config):

```yaml
# V3.0: Overseer configuration (all values are defaults — override in ~/.prime-directive/config.yaml)
overseer:
  validate_with_llm: true
  max_heartbeat_age_hours: 48.0
  scoring_weights:
    strategic_weight: 3.0
    staleness: 2.0
    focus_bonus: 2.5
    deadline_urgency: 1.5
    blocker_status: 1.0
    dependency_pressure: 1.5
    role_weight: 0.5
```

### 7.4 AI Provider Reuse

V3.0 does not introduce new AI provider code. Both heartbeat generation and LLM validation use the existing `core/ai_providers.py` infrastructure:

- **Heartbeat generation** uses `generate_ollama_response()` or `generate_openai_response()` with the cheap model, identical to SITREP generation. The only difference is the prompt.
- **LLM validation** uses the same functions with the HQ model, identical to `--hq` SITREP generation. The only difference is the prompt and the expected response format (structured JSON instead of free text).
- Both calls go through `check_budget()` before execution and log to `AIUsageLog` after completion.
- Both calls use `httpx.AsyncClient` for non-blocking HTTP.
- Fallback behavior (Ollama → OpenAI) applies to both.

This means V3.0 inherits all of V1.x's AI resilience: retry with exponential backoff, provider fallback, budget enforcement, and full cost auditing.

### 7.5 Shell Integration Update

The only change to `shell_integration.zsh` is adding `'overseer'` to the completion list:

```zsh
# Before (V1.x):
local -a commands
commands=('list' 'status' 'doctor' 'freeze' 'switch')

# After (V3.0):
local -a commands
commands=('list' 'status' 'doctor' 'freeze' 'switch' 'overseer' 'sitrep' 'metrics' 'ai-usage' 'install-hooks')
```

Note: This also fixes the V1.x weakness identified in §2.1.2 where `sitrep`, `metrics`, `ai-usage`, and `install-hooks` were missing from the completion list.

### 7.6 What V3.0 Does NOT Touch

The following V1.x components are **completely untouched** by V3.0. No imports are added, no function signatures are changed, no behavior is modified:

| Component | File | Reason |
|-----------|------|--------|
| Orchestrator | `core/orchestrator.py` | Switch logic is independent of portfolio scoring |
| Git utilities | `core/git_utils.py` | Git status capture unchanged |
| Terminal capture | `core/terminal.py` | Terminal state capture unchanged |
| Tmux management | `core/tmux.py` | Session management unchanged |
| Scribe | `core/scribe.py` | SITREP generation unchanged |
| Auto-installer | `core/auto_installer.py` | Dependency detection unchanged |
| Daemon | `bin/pd_daemon.py` | Auto-freeze unchanged (heartbeats generated by freeze_logic) |
| Dependencies | `core/dependencies.py` | Smart dependency detection unchanged |
| Windsurf | `core/windsurf.py` | Editor launch unchanged |
| All existing CLI commands | `bin/pd.py` (existing functions) | freeze, switch, sitrep, metrics, doctor, status, list, ai-usage, install-hooks — unchanged |

---

## 8. LLM Prompt Engineering

V3.0 introduces two new LLM interaction points, each with carefully designed prompts. This section documents the full prompt templates, expected response formats, parsing logic, and failure handling for both.

### 8.1 Heartbeat Generation Prompt

**When called:** During `pd freeze`, after the `ContextSnapshot` is saved.  
**Model:** Cheap model (`ai_model`, e.g., `qwen2.5-coder` or `gpt-4o-mini`).  
**Token budget:** ~500 input tokens, ~200 output tokens.  
**Purpose:** Compress a snapshot into a structured JSON heartbeat for efficient consumption by the scoring pipeline.

#### 8.1.1 System Prompt

```
You are a development status classifier. Given a snapshot of a developer's
current project state, produce a JSON object with exactly these fields:

- "status": one of "ACTIVE", "BLOCKED", "IDLE", "COMPLETED"
  - ACTIVE: developer is currently working, recent changes visible
  - BLOCKED: an explicit blocker or failure is mentioned
  - IDLE: no significant recent activity
  - COMPLETED: a milestone, merge, or release was just completed
- "summary": 1-2 sentences describing the current tactical state
- "blocker": if status is BLOCKED, describe the blocker in one sentence. null otherwise.
- "eta_minutes": estimated minutes until next milestone if determinable. null otherwise.
- "confidence": your confidence in this assessment, 0.0 to 1.0

Respond with ONLY the JSON object. No markdown, no explanation.
```

#### 8.1.2 User Prompt Template

```
Project: {repo_id}

Git Status:
{git_status_summary}

Terminal Context:
{terminal_last_command}
{terminal_output_summary}

AI SITREP:
{ai_sitrep}

Developer Notes:
Objective: {human_objective or "Not provided"}
Blocker: {human_blocker or "Not provided"}
Next Step: {human_next_step or "Not provided"}
Additional: {human_note or "Not provided"}
```

#### 8.1.3 Response Parsing

```python
def parse_heartbeat_response(raw: str, repo_id: str, snapshot_id: int) -> RepositoryHeartbeat:
    """Parse LLM response into a RepositoryHeartbeat object."""
    try:
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]

        data = json.loads(cleaned)

        status = HeartbeatStatus(data.get("status", "IDLE"))
        summary = str(data.get("summary", "No summary available"))[:500]
        blocker = data.get("blocker")
        eta = data.get("eta_minutes")
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return RepositoryHeartbeat(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=status,
            summary=summary,
            blocker=str(blocker) if blocker else None,
            eta_minutes=int(eta) if eta is not None else None,
            confidence=confidence,
            raw_json=raw,
        )
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Heartbeat parse failed for {repo_id}: {e}")
        return RepositoryHeartbeat(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=HeartbeatStatus.IDLE,
            summary="Heartbeat generation produced unparseable output",
            confidence=0.0,
            raw_json=raw,
        )
```

**Key design decisions:**
- **Markdown stripping:** Many LLMs wrap JSON in ` ```json ` fences despite instructions. The parser handles this gracefully.
- **Fallback to IDLE:** If parsing fails entirely, the heartbeat is still saved with `IDLE` status and `confidence=0.0`. This ensures the scoring pipeline always has data, even if low-quality.
- **Raw JSON preserved:** The original LLM response is stored in `raw_json` for debugging. If the parser consistently fails for a particular model, the raw responses can be examined to adjust the prompt.
- **Length capping:** Summary is capped at 500 characters to prevent runaway LLM output from bloating the database.

### 8.2 Strategic Validation Prompt

**When called:** During `pd overseer` Stage 5, after scoring is complete.  
**Model:** Expensive model (`ai_model_hq`, e.g., `gpt-4o`).  
**Token budget:** ~2000–4000 input tokens, ~500 output tokens.  
**Purpose:** Validate the algorithm's ranked output against the developer's stated strategy and flag misalignments.

#### 8.2.1 System Prompt

```
You are a strategic advisor for a solo developer managing multiple software
projects. You have been given:

1. A ranked list of projects with scores from a deterministic algorithm
2. The developer's stated strategic goals, constraints, and deadlines
3. The current tactical state of each project

Your job is to VALIDATE the ranking against the strategy. You do NOT
re-rank the projects. Instead, you:

- Identify MISALIGNMENTS where the ranking contradicts stated strategy
- Flag RISKS that the algorithm cannot detect (e.g., unstated dependencies,
  deadline pressure, team coordination issues)
- Provide a single RECOMMENDATION for what the developer should do right now

Respond with ONLY a JSON object in this exact format:
{
  "alignment_assessment": "ALIGNED" | "MISALIGNED" | "PARTIALLY_ALIGNED",
  "misalignments": [
    {
      "project_id": "string",
      "issue": "string describing the misalignment",
      "severity": "HIGH" | "MEDIUM" | "LOW"
    }
  ],
  "recommendation": "1-2 sentence actionable recommendation",
  "confidence": 0.0-1.0
}

Rules:
- "misalignments" MUST be an empty array [] if alignment_assessment is "ALIGNED"
- Every misalignment MUST reference a valid project_id from the input
- severity HIGH = contradicts stated constraint or threatens deadline
- severity MEDIUM = suboptimal allocation but not harmful
- severity LOW = minor observation
- confidence reflects how well you understand the strategic context
```

#### 8.2.2 User Prompt Template (Strategic Brief)

```
=== STRATEGIC CONTEXT ===
Focus Project: {strategy.focus}
Deadline: {strategy.deadline or "None set"}
Days Remaining: {strategy.days_until_deadline or "N/A"}

Constraints:
{for c in strategy.constraints:}
- {c}
{endfor}

Additional Context:
{strategy.body or "None provided"}

=== RANKED PROJECTS (by algorithm) ===
{for project in scored_projects:}
{project.rank}. [{project.project_id}] {project.category} (Score: {project.score}/10)
   Role: {project.role} | Weight: {project.strategic_weight}
   Status: {project.heartbeat.status if heartbeat else "NO HEARTBEAT"}
   Summary: {project.heartbeat.summary if heartbeat else "No recent data"}
   Blocker: {project.heartbeat.blocker if heartbeat and heartbeat.blocker else "None"}
   Action: {project.action_directive}
{endfor}

=== DEPENDENCY GRAPH ===
{for pid, project in empire.projects.items():}
{pid} depends on: {project.depends_on or "nothing"}
{endfor}
```

#### 8.2.3 Response Parsing

```python
def parse_validation_response(raw: str) -> ValidationResult:
    """Parse LLM strategic validation response."""
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]

        data = json.loads(cleaned)

        assessment = data.get("alignment_assessment", "PARTIALLY_ALIGNED")
        if assessment not in ("ALIGNED", "MISALIGNED", "PARTIALLY_ALIGNED"):
            assessment = "PARTIALLY_ALIGNED"

        misalignments = []
        for m in data.get("misalignments", []):
            misalignments.append(Misalignment(
                project_id=str(m.get("project_id", "unknown")),
                issue=str(m.get("issue", "Unspecified issue")),
                severity=str(m.get("severity", "LOW")),
            ))

        return ValidationResult(
            alignment_assessment=assessment,
            misalignments=misalignments,
            recommendation=str(data.get("recommendation", "")),
            confidence=float(data.get("confidence", 0.5)),
            raw_json=raw,
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Validation parse failed: {e}")
        return ValidationResult(
            alignment_assessment="PARTIALLY_ALIGNED",
            misalignments=[],
            recommendation="LLM validation produced unparseable output. Review ranking manually.",
            confidence=0.0,
            raw_json=raw,
        )
```

### 8.3 Prompt Engineering Principles

Both prompts follow these principles, derived from V1.x's experience with SITREP generation:

1. **JSON-only response.** Requesting "ONLY the JSON object" with "No markdown, no explanation" reduces the chance of free-text preambles that break parsing. The parser still handles markdown fences as a fallback.

2. **Explicit field enumeration.** Every field in the expected response is listed with its type, allowed values, and semantics. This reduces ambiguity and improves compliance across models (Ollama local models are less instruction-following than GPT-4o).

3. **Constrained role.** The strategic validator is explicitly told "You do NOT re-rank the projects." This prevents the LLM from overriding the deterministic algorithm, maintaining the Algorithm-First principle (§3.2).

4. **Structured input.** The strategic brief uses clear section headers (`=== STRATEGIC CONTEXT ===`, `=== RANKED PROJECTS ===`) and consistent formatting to help the LLM parse the context. This is more reliable than embedding everything in a natural language narrative.

5. **Graceful fallback.** Both parsers produce valid (if low-quality) output on parse failure, ensuring the pipeline never crashes due to LLM misbehavior. The `confidence=0.0` signal tells the renderer to flag the output as unreliable.

### 8.4 Model-Specific Considerations

| Model | Heartbeat Quality | Validation Quality | Notes |
|-------|------------------|--------------------|-------|
| `qwen2.5-coder` (Ollama) | Good | Not recommended | Fast, free, good at JSON extraction. Use for heartbeats. |
| `gpt-4o-mini` (OpenAI) | Excellent | Good | Best cheap option. JSON compliance is near-perfect. |
| `gpt-4o` (OpenAI) | Excellent | Excellent | Best for strategic validation. Understands nuanced constraints. |
| `claude-3.5-sonnet` (Anthropic) | Excellent | Excellent | Alternative HQ model. Strong at structured reasoning. |
| `llama3` (Ollama) | Fair | Poor | Struggles with JSON-only instruction. Needs more prompt engineering. |

V3.0 does not hardcode model names — it uses whatever is configured in `ai_model` and `ai_model_hq`. The prompt design is model-agnostic but optimized for the JSON compliance characteristics of GPT-4o family and Qwen models.

---

## 9. CLI User Experience

This section specifies the `pd overseer` command interface, the progressive onboarding wizard, and the full output format with examples.

### 9.1 Command Interface

```
pd overseer [OPTIONS]

Options:
  --verbose / --no-verbose    Show detailed score breakdowns per project (default: --no-verbose)
  --no-validate               Skip LLM strategic validation (Stage 5). Produces deterministic-only output.
  --json                      Output raw JSON instead of formatted Rich output. Useful for scripting.
  --help                      Show help message and exit.
```

**No required arguments.** The command reads all inputs from well-known file paths and the database. This is intentional — `pd overseer` should be a zero-friction command that the developer runs habitually, like `git status`.

**Exit codes:**
- `0`: Report generated successfully (with or without LLM validation).
- `1`: Fatal error (empire.yaml parse failure, dependency cycle, database error).
- `2`: Empire not found (prints setup wizard instructions).

### 9.2 Progressive Onboarding Wizard

When `pd overseer` is invoked without `empire.yaml`, it does not simply error out. Instead, it guides the developer through setup.

#### 9.2.1 First Run (No empire.yaml)

```
$ pd overseer

╭──────────────────────────────────────────────────────────╮
│  🛡️  PRIME DIRECTIVE — Grand Strategist Setup            │
│                                                          │
│  No empire.yaml found at ~/.prime-directive/empire.yaml  │
│                                                          │
│  The Grand Strategist needs to know about your projects  │
│  to provide portfolio-level recommendations.             │
│                                                          │
│  Would you like to generate empire.yaml now? [Y/n]       │
╰──────────────────────────────────────────────────────────╯
```

If the user answers `Y`, the wizard walks through each repository in `config.yaml`:

```
Found 4 repositories in your configuration:

Setting up: rna-predict (~/dev/research/rna-predict)
  Domain (e.g., research, infra, product): research
  Role [RESEARCH/INFRASTRUCTURE/MAINTENANCE/EXPERIMENTAL]: RESEARCH
  Strategic Weight [CRITICAL/HIGH/MEDIUM/LOW]: CRITICAL
  Description (1-2 sentences): Primary RNA structure prediction model for Q1 demo
  Dependencies (comma-separated project IDs, or empty): black-box

Setting up: black-box (~/dev/infra/black-box)
  Domain: core-infra
  Role: INFRASTRUCTURE
  Strategic Weight: HIGH
  Description: Core data pipeline and API service
  Dependencies:

[... repeats for each project ...]

✅ empire.yaml written to ~/.prime-directive/empire.yaml
   Dependency graph validated — no cycles detected.

💡 Next step: Create ~/.prime-directive/strategy.md to enable
   strategic validation. Run 'pd overseer' again to see your
   first portfolio report.
```

#### 9.2.2 Second Run (empire.yaml exists, no strategy.md)

```
$ pd overseer

>>> 🛡️ THE OVERSEER REPORT <<<
Generated: 2025-03-08 20:15:00 UTC

──── Ranked Projects ────────────────────────────────

1. [rna-predict] 🔥 CRITICAL (Score: 7.2/10)
   👉 Last freeze was 18h ago. Consider running 'pd freeze rna-predict'.

2. [black-box] ⚠️ MONITOR (Score: 4.8/10)
   👉 No immediate action needed. Review if staleness increases.

3. [prime-directive] ⚠️ MONITOR (Score: 4.1/10)
   👉 No immediate action needed. Review if staleness increases.

4. [bluethumb] 💤 DEPRIORITIZE (Score: 2.3/10)
   👉 Safe to ignore. Only address critical bugs.

──── Configuration Health ───────────────────────────

  ✅ empire.yaml    Loaded (4 projects, 2 dependencies)
  ⚠️  strategy.md   NOT FOUND
     → Create ~/.prime-directive/strategy.md to enable:
       • Strategic focus boosting
       • Deadline urgency tracking
       • LLM misalignment detection
  ✅ Heartbeats     3/4 projects have recent heartbeats
  ⚠️  Heartbeat      rna-predict: stale (18h old)

──── Cost ───────────────────────────────────────────

  LLM validation: skipped (no strategy.md)
  Budget remaining: $8.42 / $10.00 this month
```

#### 9.2.3 Full Run (empire.yaml + strategy.md + LLM validation)

```
$ pd overseer

>>> 🛡️ THE OVERSEER REPORT <<<
Generated: 2025-03-08 20:15:00 UTC
Strategic Focus: rna-predict | Deadline: 2025-03-14 (6 days)

🚨 MISALIGNMENT DETECTED 🚨
  [bluethumb] Strategy says "maintenance-only — critical bugs only"
  but heartbeat shows active feature development (CSS refactoring).
  Severity: HIGH

──── Ranked Projects ────────────────────────────────

1. [rna-predict] 🔥 CRITICAL (Score: 9.6/10)
   Status: BLOCKED — Gradient explosion in transformer layer
   👉 You are blocked on: gradient explosion causing NaN losses.
      This is your top priority.

2. [black-box] ⚠️ MONITOR (Score: 5.2/10)
   Status: ACTIVE — v2.3 API migration in progress
   👉 No active work needed, but verify API stability as
      rna-predict depends on it.

3. [prime-directive] ⚠️ MONITOR (Score: 4.1/10)
   Status: ACTIVE — Writing V3.0 architecture doc
   👉 No immediate action needed. Review if staleness increases.

4. [bluethumb] 💤 DEPRIORITIZE (Score: 1.8/10)
   Status: ACTIVE — CSS refactoring
   👉 Safe to ignore. Only address critical bugs.

──── Strategic Validation (AI) ──────────────────────

  Assessment: PARTIALLY_ALIGNED (confidence: 0.85)
  Recommendation: "Focus exclusively on rna-predict today. The
  gradient explosion blocker is the only thing standing between
  you and the Friday demo. Stop all bluethumb work immediately."

──── Configuration Health ───────────────────────────

  ✅ empire.yaml    Loaded (4 projects, 2 dependencies)
  ✅ strategy.md    Loaded (focus: rna-predict, deadline: 2025-03-14)
  ✅ Heartbeats     4/4 projects have recent heartbeats
  ✅ LLM Validation Completed (gpt-4o)

──── Cost ───────────────────────────────────────────

  LLM validation: 2,847 tokens ($0.014)
  Budget remaining: $8.41 / $10.00 this month
```

### 9.3 Verbose Mode (`--verbose`)

When `--verbose` is passed, each project in the ranked list includes a full score breakdown:

```
1. [rna-predict] 🔥 CRITICAL (Score: 9.6/10)
   Status: BLOCKED — Gradient explosion in transformer layer
   👉 You are blocked on: gradient explosion causing NaN losses.

   Score Breakdown:
     strategic_weight:    3.0/3.0  (CRITICAL → 1.0)
     staleness:           1.6/2.0  (18h old → 0.8)
     focus_bonus:         2.5/2.5  (strategy focus)
     deadline_urgency:    1.3/1.5  (6 days → 0.57)
     blocker_status:      1.0/1.0  (BLOCKED)
     dependency_pressure: 0.0/1.5  (no blocked dependents)
     role_weight:         0.5/0.5  (RESEARCH → 1.0)
```

### 9.4 JSON Mode (`--json`)

When `--json` is passed, the entire report is emitted as a single JSON object to stdout, suitable for piping to `jq` or consumption by other tools:

```json
{
  "timestamp": "2025-03-08T20:15:00Z",
  "strategy": {
    "focus": "rna-predict",
    "deadline": "2025-03-14",
    "days_remaining": 6
  },
  "projects": [
    {
      "project_id": "rna-predict",
      "rank": 1,
      "score": 9.6,
      "category": "CRITICAL",
      "action_directive": "You are blocked on: gradient explosion causing NaN losses. This is your top priority.",
      "heartbeat": {
        "status": "BLOCKED",
        "summary": "Gradient explosion in transformer layer.",
        "blocker": "Gradient explosion causing NaN losses after 50 steps",
        "confidence": 0.8
      },
      "score_breakdown": {
        "strategic_weight": 3.0,
        "staleness": 1.6,
        "focus_bonus": 2.5,
        "deadline_urgency": 1.3,
        "blocker_status": 1.0,
        "dependency_pressure": 0.0,
        "role_weight": 0.5
      }
    }
  ],
  "validation": {
    "alignment_assessment": "PARTIALLY_ALIGNED",
    "misalignments": [
      {
        "project_id": "bluethumb",
        "issue": "Strategy says maintenance-only but heartbeat shows active feature development.",
        "severity": "HIGH"
      }
    ],
    "recommendation": "Focus exclusively on rna-predict today.",
    "confidence": 0.85
  },
  "config_health": {
    "empire_loaded": true,
    "strategy_loaded": true,
    "heartbeat_coverage": "4/4",
    "llm_validation": "completed"
  },
  "cost": {
    "tokens_used": 2847,
    "cost_usd": 0.014,
    "budget_remaining_usd": 8.41
  }
}
```

### 9.5 Integration with `pd doctor`

V3.0 extends the existing `pd doctor` command to check V3.0-specific configuration:

```
$ pd doctor

[... existing V1.x checks ...]

V3.0 Grand Strategist:
  ✅ empire.yaml exists at ~/.prime-directive/empire.yaml
  ✅ empire.yaml parses without errors (4 projects)
  ✅ Dependency graph is acyclic
  ⚠️  strategy.md not found at ~/.prime-directive/strategy.md
  ✅ RepositoryHeartbeat table exists in database
  ✅ 3/4 projects have heartbeats less than 24h old
  ⚠️  rna-predict heartbeat is 18h old (threshold: 24h)
```

This allows developers to diagnose V3.0 configuration issues without running the full `pd overseer` pipeline.

---

## 10. Cost Model, Performance, and Testing Strategy

### 10.1 Cost Model

V3.0 adds two new LLM touchpoints to the system. This section provides a detailed cost analysis to demonstrate that V3.0 stays within the existing `ai_monthly_budget_usd` ceiling (default: $10.00/month).

#### 10.1.1 Per-Operation Cost Breakdown

| Operation | Model | Input Tokens | Output Tokens | Cost/Call | Frequency | Monthly Cost |
|-----------|-------|-------------|--------------|-----------|-----------|-------------|
| SITREP generation (V1.x) | `qwen2.5-coder` (Ollama) | ~800 | ~150 | $0.00 (local) | ~20/day | $0.00 |
| SITREP generation (V1.x fallback) | `gpt-4o-mini` | ~800 | ~150 | ~$0.0003 | ~5/day | ~$0.05 |
| **Heartbeat generation (V3.0)** | `qwen2.5-coder` (Ollama) | ~500 | ~100 | $0.00 (local) | ~20/day | $0.00 |
| **Heartbeat generation (V3.0 fallback)** | `gpt-4o-mini` | ~500 | ~100 | ~$0.0002 | ~5/day | ~$0.03 |
| **LLM validation (V3.0)** | `gpt-4o` | ~3000 | ~300 | ~$0.014 | ~3/day | ~$12.60 |

**Key observations:**

- **Heartbeat generation is essentially free** when using a local Ollama model. Even with OpenAI fallback, it adds ~$0.03/month — negligible.
- **LLM validation is the only significant cost.** At ~$0.014 per call and 3 calls per day, it would cost ~$12.60/month — **exceeding the default $10 budget**.

**Mitigation strategies:**

1. **Budget-gated execution.** LLM validation is skipped when the monthly budget would be exceeded, with the output clearly labeled. The deterministic ranking (Stages 1–4) is always available at zero cost.
2. **Frequency discipline.** Most developers will run `pd overseer` 1–2 times per day (morning planning, mid-afternoon check), not continuously. At 2 calls/day, the monthly cost drops to ~$8.40.
3. **`--no-validate` flag.** Developers can explicitly skip LLM validation when they just want the deterministic ranking. This is the recommended usage for frequent checks.
4. **Model selection.** Using `gpt-4o-mini` for validation instead of `gpt-4o` reduces the cost to ~$0.002/call (~$0.18/month at 3 calls/day), though with reduced strategic reasoning quality.

#### 10.1.2 Cost Tracking

All V3.0 LLM calls are logged to the existing `AIUsageLog` table with appropriate `provider`, `model`, `input_tokens`, `output_tokens`, and `cost_estimate_usd` fields. The `pd ai-usage` command displays all costs, including V3.0 heartbeat and validation costs, without modification — V3.0 costs flow through the same tracking infrastructure as V1.x costs.

### 10.2 Performance Budgets

V3.0 must not degrade the user experience of existing V1.x operations. The following performance budgets are enforced:

| Operation | Budget | Breakdown |
|-----------|--------|-----------|
| `pd freeze` (with heartbeat) | < 5s total | V1.x freeze (~3s) + heartbeat generation (~200ms async, concurrent with DB write) |
| `pd overseer` (no LLM) | < 1s | File I/O (~50ms) + DB queries (~100ms) + scoring (~1ms) + rendering (~50ms) |
| `pd overseer` (with LLM) | < 8s | Above + LLM call (~2–5s depending on model and provider) |
| Empire/strategy parsing | < 50ms | YAML/markdown parsing is I/O-bound, not compute-bound |
| Dependency graph (Tarjan's) | < 1ms | O(V+E) on typical portfolios of 5–15 projects |

**Heartbeat generation does not block freeze completion.** The heartbeat is generated after the snapshot is saved to the database. If heartbeat generation is slow or fails, the freeze has already succeeded. The user sees "Snapshot saved" immediately; the heartbeat is a background operation.

**`pd overseer` Stages 1–4 are CPU-bound and fast.** The only I/O in the deterministic pipeline is reading two config files and querying the database. For typical portfolios, this completes in under 200ms. Stage 5 (LLM validation) dominates the total time when enabled.

### 10.3 Testing Strategy

V3.0 introduces 8 new modules (`empire.py`, `strategy.py`, `heartbeat.py`, `graph.py`, `scoring.py`, `overseer.py`, `validator.py`, `renderer.py`). Each requires comprehensive testing. The test architecture follows V1.x's conventions: `pytest` with `asyncio_mode = "auto"`, mock mode for LLM calls, and `tmp_path` fixtures for database isolation.

#### 10.3.1 Unit Tests

| Module | Test File | Key Test Cases | Est. Tests |
|--------|-----------|---------------|------------|
| `core/empire.py` | `tests/test_empire.py` | Valid parse, missing fields, invalid role/weight enums, unknown project IDs, version mismatch | 12 |
| `core/strategy.py` | `tests/test_strategy.py` | Valid parse, missing frontmatter, invalid focus project, past deadline warning, malformed YAML | 10 |
| `core/graph.py` | `tests/test_graph.py` | Acyclic graph, single cycle, multi-cycle, self-loop, orphan detection, empty graph, single node | 10 |
| `core/scoring.py` | `tests/test_scoring.py` | Each factor in isolation, all-max score, all-min score, custom weights, deadline edge cases (0 days, negative, None), focus bonus toggle | 15 |
| `core/heartbeat.py` | `tests/test_heartbeat.py` | Valid JSON parse, malformed JSON fallback, markdown-wrapped JSON, missing fields, confidence clamping, summary truncation | 10 |
| `core/validator.py` | `tests/test_validator.py` | Valid JSON parse, malformed JSON fallback, ALIGNED/MISALIGNED/PARTIALLY_ALIGNED, empty misalignments array, invalid severity | 8 |
| `core/renderer.py` | `tests/test_renderer.py` | Rich output format verification, JSON mode output, verbose mode score breakdown, configuration health display | 6 |
| `core/overseer.py` | `tests/test_overseer.py` | Full pipeline with mocked LLM, pipeline without strategy.md, pipeline without heartbeats, budget-exceeded skip, --no-validate flag | 8 |

**Estimated new unit tests: ~79**

#### 10.3.2 Integration Tests

| Test Scenario | Description |
|---------------|-------------|
| Full pipeline, mock mode | Run `pd overseer` with mock LLM responses. Verify output format, score ordering, and configuration health. |
| Heartbeat generation in freeze | Run `pd freeze` with `empire.yaml` present. Verify `RepositoryHeartbeat` row is created in DB. |
| Heartbeat fallback in freeze | Run `pd freeze` with LLM error. Verify freeze succeeds and heartbeat failure is logged as warning. |
| Empire validation against config | Create `empire.yaml` with project IDs not in `config.yaml`. Verify error message lists invalid IDs. |
| Dependency cycle detection | Create `empire.yaml` with a cycle (A→B→C→A). Verify error message prints the cycle. |
| Progressive degradation | Run `pd overseer` with no `strategy.md`. Verify scoring works, LLM validation is skipped, and configuration health shows the gap. |
| Budget enforcement | Set `ai_monthly_budget_usd: 0.01` and run `pd overseer`. Verify LLM validation is skipped with budget message. |

#### 10.3.3 Scoring Algorithm Property Tests

The scoring algorithm is a pure function, making it ideal for property-based testing with `hypothesis`:

```python
from hypothesis import given, strategies as st

@given(
    strategic_weight=st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
    staleness=st.floats(min_value=0.0, max_value=1.0),
    is_focus=st.booleans(),
    days_until_deadline=st.one_of(st.none(), st.integers(min_value=-7, max_value=30)),
    has_blocker=st.booleans(),
    has_blocked_dependent=st.booleans(),
    role=st.sampled_from(["RESEARCH", "INFRASTRUCTURE", "MAINTENANCE", "EXPERIMENTAL"]),
)
def test_score_is_bounded(strategic_weight, staleness, is_focus,
                          days_until_deadline, has_blocker,
                          has_blocked_dependent, role):
    """Score must always be in [0.0, 10.0]."""
    state = make_project_state(...)
    score = compute_score(state, ScoringWeights())
    assert 0.0 <= score <= 10.0


def test_focus_project_scores_higher():
    """The focus project should always score >= non-focus project, all else equal."""
    base = make_project_state(is_focus=False)
    focused = make_project_state(is_focus=True)
    assert compute_score(focused, ScoringWeights()) >= compute_score(base, ScoringWeights())


def test_critical_beats_low():
    """A CRITICAL project should always outscore a LOW project, all else equal."""
    critical = make_project_state(strategic_weight="CRITICAL")
    low = make_project_state(strategic_weight="LOW")
    assert compute_score(critical, ScoringWeights()) > compute_score(low, ScoringWeights())
```

#### 10.3.4 Test Infrastructure

- **Mock LLM responses:** Heartbeat and validation tests use pre-recorded JSON responses, not live LLM calls. This ensures tests are deterministic, fast, and free.
- **Temporary databases:** Each test creates an isolated SQLite database in `tmp_path`, preventing cross-test contamination.
- **Config fixtures:** Test-specific `empire.yaml` and `strategy.md` files are written to `tmp_path` and injected via Hydra overrides.
- **Existing test suite unchanged:** V3.0 tests are additive. The existing 81+ V1.x tests continue to pass without modification.

---

## 11. Implementation Roadmap

V3.0 is implemented in four phases, each delivering incremental value. Every phase ends with a working system — there are no phases that produce only intermediate artifacts. The phases are ordered by dependency: each phase builds on the previous one's output.

### 11.1 Phase 1: Data Foundation

**Goal:** Add the `RepositoryHeartbeat` table, implement heartbeat generation during `pd freeze`, and create the `empire.yaml` parser with validation.

**Deliverables:**
1. `core/empire.py` — Parser for `empire.yaml` with full validation (role enums, weight enums, project ID cross-reference against `config.yaml`, dependency reference validation).
2. `core/graph.py` — Dependency DAG construction with Tarjan's SCC cycle detection and topological sort.
3. `RepositoryHeartbeat` model added to `core/db.py` with `HeartbeatStatus` enum.
4. `core/heartbeat.py` — Heartbeat generation function (`generate_heartbeat`) and response parser (`parse_heartbeat_response`). Query function for latest heartbeat per project.
5. Integration into `freeze_logic` in `bin/pd.py` — conditional heartbeat generation when `empire.yaml` exists.
6. `EmpireConfig` and related dataclasses added to `core/config.py`.
7. Tests: `test_empire.py`, `test_graph.py`, `test_heartbeat.py`.

**Dependencies:** None (builds on existing V1.x).  
**Estimated effort:** 2–3 sessions.  
**Value delivered:** Every `pd freeze` now generates structured heartbeats, building the data foundation that `pd overseer` will consume. The developer can verify heartbeats are being generated via direct DB inspection.

### 11.2 Phase 2: Scoring Engine

**Goal:** Implement the deterministic scoring algorithm and the `pd overseer` command (Stages 1–4 only, no LLM validation).

**Deliverables:**
1. `core/strategy.py` — Parser for `strategy.md` with YAML frontmatter extraction, field validation, and freeform body capture.
2. `core/scoring.py` — Pure scoring function with all 7 factors, configurable weights, and score breakdown generation.
3. `core/renderer.py` — Rich-formatted terminal output for the overseer report, including ranked project list, configuration health, and cost footer.
4. `core/overseer.py` — Pipeline orchestrator for Stages 1–4 (load context, build graph, compute scores, classify & label).
5. `pd overseer` command added to `bin/pd.py` with `--verbose`, `--json`, and `--no-validate` flags.
6. `ScoringWeightsConfig` and `OverseerConfig` dataclasses added to `core/config.py`.
7. Default `overseer` section added to `conf/config.yaml`.
8. Tests: `test_strategy.py`, `test_scoring.py`, `test_renderer.py`, `test_overseer.py` (Stages 1–4).

**Dependencies:** Phase 1 (heartbeats and empire parser must exist).  
**Estimated effort:** 2–3 sessions.  
**Value delivered:** `pd overseer` produces a deterministic, ranked portfolio report. The developer can see which project needs attention, why (score breakdown), and what to do (action directive). This works entirely offline with zero LLM cost.

### 11.3 Phase 3: LLM Validation

**Goal:** Add Stage 5 (LLM strategic validation) to the `pd overseer` pipeline.

**Deliverables:**
1. `core/validator.py` — Strategic brief construction, LLM call via existing `ai_providers`, and structured JSON response parsing.
2. Stage 5 integration into `core/overseer.py` — conditional execution based on `strategy.md` existence, budget availability, and `--no-validate` flag.
3. Misalignment warning rendering in `core/renderer.py`.
4. Budget enforcement for validation calls via existing `check_budget`.
5. Tests: `test_validator.py`, updated `test_overseer.py` (Stage 5 scenarios).

**Dependencies:** Phase 2 (scoring must produce ranked output for the LLM to validate).  
**Estimated effort:** 1–2 sessions.  
**Value delivered:** `pd overseer` now includes AI-powered strategic validation that catches misalignments between the algorithm's ranking and the developer's stated goals. The system provides its maximum value at this point.

### 11.4 Phase 4: Polish & Onboarding

**Goal:** Implement the progressive onboarding wizard, extend `pd doctor`, and fix V1.x shell completion.

**Deliverables:**
1. Onboarding wizard in `pd overseer` — interactive setup when `empire.yaml` is missing. Walks through each repo in `config.yaml` and writes `empire.yaml`.
2. `pd doctor` extension — V3.0 configuration health checks (empire.yaml exists/parses, graph is acyclic, strategy.md exists, heartbeat coverage and freshness).
3. Shell completion update in `shell_integration.zsh` — add `overseer`, `sitrep`, `metrics`, `ai-usage`, `install-hooks` to completion list.
4. Documentation updates — README.md, docs/index.md, CLI help text.
5. Tests: wizard interaction tests, doctor extension tests.

**Dependencies:** Phase 3 (all pipeline stages must be complete).  
**Estimated effort:** 1 session.  
**Value delivered:** Zero-friction onboarding for new users. Complete diagnostic capability. Shell UX polish.

### 11.5 Task Dependency Graph

```
Phase 1                    Phase 2              Phase 3         Phase 4
────────                   ────────             ────────        ────────

empire.py ─────┐
               │
graph.py ──────┤
               ├──→ scoring.py ──────┐
heartbeat.py ──┤                     │
               │    strategy.py ─────┤
db.py (HB) ────┤                     ├──→ validator.py ──→ wizard
               │    renderer.py ─────┤                     doctor ext
pd.py (freeze) ┘                     │                     shell comp
                    overseer.py ─────┘                     docs
                    pd.py (overseer)
                    config.py (overseer)
```

### 11.6 Migration Guide: V1.x → V3.0

V3.0 requires **zero migration steps** for existing V1.x users. The upgrade path is:

1. **Update the package.** `pip install -e .` or `uv pip install -e .` — the usual process.
2. **Database auto-migrates.** The `RepositoryHeartbeat` table is created automatically by `SQLModel.metadata.create_all()` on the next `pd freeze` or `pd overseer` invocation. No manual SQL, no migration scripts, no data loss.
3. **Config is backward-compatible.** The new `overseer` section in `conf/config.yaml` has defaults for all fields. Existing user `~/.prime-directive/config.yaml` files work without changes.
4. **All existing commands unchanged.** `pd freeze`, `pd switch`, `pd sitrep`, `pd metrics`, `pd doctor`, `pd status`, `pd list`, `pd ai-usage`, `pd install-hooks` — all behave identically.
5. **V3.0 features activate incrementally:**
   - Heartbeat generation starts automatically on next `pd freeze` if `~/.prime-directive/empire.yaml` exists.
   - `pd overseer` becomes available immediately but prints setup instructions if `empire.yaml` is missing.
   - The onboarding wizard guides the user through `empire.yaml` creation.
   - `strategy.md` is optional — `pd overseer` works without it, just with less context.

**There is no "V3.0 migration" — there is only "creating empire.yaml when you're ready."**

### 11.7 Rollback Plan

If V3.0 introduces regressions:

1. **Heartbeat generation can be disabled** by removing `empire.yaml`. The `freeze_logic` code path checks for file existence before attempting heartbeat generation.
2. **The `RepositoryHeartbeat` table is harmless** if unused. It consumes no resources and does not affect V1.x queries. It can be dropped with `DROP TABLE repositoryheartbeat;` if desired.
3. **The `pd overseer` command can be ignored.** It is a new command, not a modification of an existing one. Not running it has zero side effects.
4. **The `overseer` config section is optional.** If present in `config.yaml` but unused, it has no effect on V1.x behavior.

---

## 12. Appendices

### Appendix A: Worked Scoring Example

This appendix walks through a complete scoring calculation for a 4-project portfolio to demonstrate exactly how the algorithm produces its rankings. All inputs are shown, all calculations are explicit, and the final ranking matches the example output in §9.2.3.

#### A.1 Input State

**Empire config (`empire.yaml`):**

| Project | Role | Weight | Depends On |
|---------|------|--------|-----------|
| rna-predict | RESEARCH | CRITICAL | black-box |
| black-box | INFRASTRUCTURE | HIGH | — |
| prime-directive | INFRASTRUCTURE | MEDIUM | — |
| bluethumb | MAINTENANCE | LOW | black-box |

**Strategy (`strategy.md`):**
- Focus: `rna-predict`
- Deadline: 6 days from now
- Constraints: "bluethumb is maintenance-only"

**Heartbeats (latest):**

| Project | Status | Age | Blocker |
|---------|--------|-----|---------|
| rna-predict | BLOCKED | 18h | "Gradient explosion causing NaN losses" |
| black-box | ACTIVE | 4h | — |
| prime-directive | ACTIVE | 2h | — |
| bluethumb | ACTIVE | 8h | — |

**Dependency graph:**
- `black-box` → `rna-predict` (rna-predict depends on black-box)
- `black-box` → `bluethumb` (bluethumb depends on black-box)
- Depth: black-box=0, prime-directive=0, rna-predict=1, bluethumb=1
- `rna-predict` is BLOCKED and depends on `black-box`, so `black-box.has_blocked_dependent = True`

#### A.2 Factor Calculation

**Default weights:** strategic_weight=3.0, staleness=2.0, focus_bonus=2.5, deadline_urgency=1.5, blocker_status=1.0, dependency_pressure=1.5, role_weight=0.5

**Max possible raw score:** 3.0 + 2.0 + 2.5 + 1.5 + 1.0 + 1.5 + 0.5 = **12.0**

**rna-predict:**
| Factor | Value | × Weight | Contribution |
|--------|-------|----------|-------------|
| strategic_weight | 1.0 (CRITICAL) | × 3.0 | 3.0 |
| staleness | 18/(18+12) = 0.6 | × 2.0 | 1.2 |
| focus_bonus | 1.0 (is focus) | × 2.5 | 2.5 |
| deadline_urgency | 1.0 - (6/14) = 0.571 | × 1.5 | 0.857 |
| blocker_status | 1.0 (BLOCKED) | × 1.0 | 1.0 |
| dependency_pressure | 0.0 (no blocked dependents) | × 1.5 | 0.0 |
| role_weight | 1.0 (RESEARCH) | × 0.5 | 0.5 |
| **Raw total** | | | **9.057** |
| **Score** | (9.057 / 12.0) × 10 | | **7.5** |

**black-box:**
| Factor | Value | × Weight | Contribution |
|--------|-------|----------|-------------|
| strategic_weight | 0.75 (HIGH) | × 3.0 | 2.25 |
| staleness | 4/(4+12) = 0.25 | × 2.0 | 0.5 |
| focus_bonus | 0.0 | × 2.5 | 0.0 |
| deadline_urgency | 0.571 | × 1.5 | 0.857 |
| blocker_status | 0.0 | × 1.0 | 0.0 |
| dependency_pressure | 1.0 (rna-predict is blocked and depends on this) | × 1.5 | 1.5 |
| role_weight | 0.75 (INFRASTRUCTURE) | × 0.5 | 0.375 |
| **Raw total** | | | **5.482** |
| **Score** | (5.482 / 12.0) × 10 | | **4.6** |

**prime-directive:**
| Factor | Value | × Weight | Contribution |
|--------|-------|----------|-------------|
| strategic_weight | 0.5 (MEDIUM) | × 3.0 | 1.5 |
| staleness | 2/(2+12) = 0.143 | × 2.0 | 0.286 |
| focus_bonus | 0.0 | × 2.5 | 0.0 |
| deadline_urgency | 0.571 | × 1.5 | 0.857 |
| blocker_status | 0.0 | × 1.0 | 0.0 |
| dependency_pressure | 0.0 | × 1.5 | 0.0 |
| role_weight | 0.75 (INFRASTRUCTURE) | × 0.5 | 0.375 |
| **Raw total** | | | **3.018** |
| **Score** | (3.018 / 12.0) × 10 | | **2.5** |

**bluethumb:**
| Factor | Value | × Weight | Contribution |
|--------|-------|----------|-------------|
| strategic_weight | 0.25 (LOW) | × 3.0 | 0.75 |
| staleness | 8/(8+12) = 0.4 | × 2.0 | 0.8 |
| focus_bonus | 0.0 | × 2.5 | 0.0 |
| deadline_urgency | 0.571 | × 1.5 | 0.857 |
| blocker_status | 0.0 | × 1.0 | 0.0 |
| dependency_pressure | 0.0 | × 1.5 | 0.0 |
| role_weight | 0.25 (MAINTENANCE) | × 0.5 | 0.125 |
| **Raw total** | | | **2.532** |
| **Score** | (2.532 / 12.0) × 10 | | **2.1** |

#### A.3 Final Ranking

| Rank | Project | Score | Category |
|------|---------|-------|----------|
| 1 | rna-predict | 7.5 | 🔥 CRITICAL |
| 2 | black-box | 4.6 | ⚠️ MONITOR |
| 3 | prime-directive | 2.5 | 💤 DEPRIORITIZE |
| 4 | bluethumb | 2.1 | 💤 DEPRIORITIZE |

**Observations:**
- rna-predict scores highest because it stacks CRITICAL weight, focus bonus, deadline urgency, blocker status, and high staleness.
- black-box scores second because it has dependency pressure (rna-predict is blocked and depends on it), which the algorithm surfaces even though black-box itself is healthy.
- prime-directive and bluethumb are both deprioritized, but prime-directive's MEDIUM weight edges out bluethumb's LOW weight.

---

### Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **Empire** | The developer's complete portfolio of managed projects, defined in `empire.yaml`. |
| **Heartbeat** | A lightweight, structured JSON summary of a project's tactical state, generated by LLM during `pd freeze`. Stored in `RepositoryHeartbeat` table. |
| **Strategic Weight** | A developer-assigned importance level (CRITICAL/HIGH/MEDIUM/LOW) for a project, used as a multiplier in scoring. |
| **Project Role** | The functional classification of a project (RESEARCH/INFRASTRUCTURE/MAINTENANCE/EXPERIMENTAL), affecting scoring via role weight factor. |
| **Staleness** | A measure of how long since a project's last freeze/heartbeat. Ranges 0.0 (just frozen) to 1.0 (>48h since last activity). |
| **Focus Project** | The project designated in `strategy.md` as the developer's current primary attention target. Receives a scoring bonus. |
| **Dependency Pressure** | A scoring factor that activates when a project you own is blocking another project (the dependent has BLOCKED status). |
| **Strategic Brief** | The JSON document sent to the HQ LLM during Stage 5, containing the ranked projects, strategy context, and dependency graph. |
| **Misalignment** | A discrepancy between the algorithm's ranking and the developer's stated strategy, detected by the LLM validator. |
| **Overseer Report** | The formatted terminal output of `pd overseer`, containing ranked projects, scores, directives, and configuration health. |

---

### Appendix C: Design Decision Log

| Decision | Alternatives Considered | Rationale |
|----------|------------------------|-----------|
| `empire.yaml` as overlay, not replacement for `config.yaml` | Replace `config.yaml` entirely (V2.1 proposal) | Zero breaking changes to V1.x. Projects can opt into portfolio management incrementally. |
| Semi-structured `strategy.md` (YAML frontmatter + freeform body) | Fully freeform (V2.1), fully structured YAML | Frontmatter gives the algorithm deterministic inputs. Body gives the LLM nuanced context. Best of both worlds. |
| Tarjan's algorithm for cycle detection | Simple DFS, Kahn's algorithm | Tarjan's detects all SCCs in one pass. For tiny graphs (5–15 nodes) the choice is irrelevant, but Tarjan's is the canonical algorithm. |
| Heartbeat as separate DB table (not embedded in ContextSnapshot) | Add columns to ContextSnapshot | Separation of concerns. Heartbeats are LLM-generated summaries with different schema/lifecycle than raw snapshots. Heartbeats can be regenerated; snapshots are immutable records. |
| LLM validates but does not rank | LLM produces the ranking | Algorithm-first ensures auditability and reproducibility. LLM-as-validator catches strategic misalignment without creating a black box. |
| Sigmoid-like staleness curve (`age / (age + 12)`) | Linear, exponential, step function | Smooth curve with meaningful inflection at ~12h. Linear overweights very fresh projects. Exponential is too aggressive. Step function loses nuance. |
| Default scoring weights favor strategic_weight (3.0) and focus_bonus (2.5) | Equal weights, domain-specific presets | The developer's explicit declarations of importance (strategic weight) and current focus should dominate. Staleness (2.0) is the secondary driver. |
| `--json` output mode | File export, dashboard UI, Markdown output | JSON is the universal interchange format. Piping to `jq` covers filtering needs. File/dashboard/Markdown can be built on top of JSON output later. |
| Budget-gated LLM validation (skip when over budget) | Hard block entire command, reduce model quality | The deterministic ranking is always valuable. Blocking the entire command because of budget would punish the user. Automatic model downgrade would change behavior unpredictably. |

---

### Appendix D: Future Considerations (Out of Scope for V3.0)

The following features are explicitly **not** in V3.0 but are noted for potential future versions:

1. **Multi-user support.** V3.0 is single-developer only. Supporting teams would require shared databases, conflict resolution for `empire.yaml`, and per-user `strategy.md` files.

2. **Time-series analysis.** Heartbeat history could be used to visualize project health trends over time (e.g., "rna-predict has been BLOCKED for 3 days"). V3.0 stores the data but does not analyze trends.

3. **Automated `strategy.md` updates.** An LLM could suggest updates to `strategy.md` based on observed project activity (e.g., "You've been working on bluethumb for 2 days despite saying maintenance-only. Update strategy?").

4. **MCP integration.** Exposing the overseer report via Model Context Protocol would allow IDE-integrated AI assistants to access portfolio context directly.

5. **Notification/alerting.** The daemon could run `pd overseer` periodically and send desktop notifications when a project enters CRITICAL status or a misalignment is detected.

6. **Weight auto-tuning.** Track whether the developer follows or overrides the overseer's recommendations, and adjust scoring weights based on observed behavior patterns.

7. **Cross-portfolio dependency tracking.** Track dependencies between projects owned by different developers (e.g., "your project depends on Alice's API, which hasn't been updated in a week").

---

*End of Document*

**Document checksum:** V3.0 Grand Strategist Protocol — 12 sections, ~2000 lines  
**Status:** Ready for implementation per Phase 1 → Phase 4 roadmap (§11)

