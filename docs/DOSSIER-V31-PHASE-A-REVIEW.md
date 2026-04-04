# Operator Dossier V3.1 Phase A — Comprehensive Diff Review

**Branch:** `feature/operator-dossier-v31-phase-a`
**PR:** [#16](https://github.com/ImmortalDemonGod/prime-directive/pull/16)
**Base:** `main`
**Date:** 2025-07-XX
**Diff Stats:** ~7,784 insertions(+), 3 deletions(-)

---

## 1. Executive Summary

This branch implements Phase A of the Operator Identity Protocol (V3.1), introducing a persistent operator dossier system to the Prime Directive CLI. The dossier captures a 5-layer identity model — human identity, technical capabilities, professional network, strategic positioning, and a machine-matchable connection surface — stored as `~/.prime-directive/operator_dossier.yaml`.

### 1.1 Scope of Changes

The branch delivers six major capabilities:

1. **Dossier Schema & Data Model** — A complete 5-layer dataclass hierarchy in `identity.py` with YAML serialization, validation, and tag normalization.
2. **Empire Configuration** — A new `empire.yaml` schema for declaring project metadata (roles, strategic weights, dependencies) with cycle detection.
3. **Multi-Language Skill Scanning** — Static analysis of `pyproject.toml`, `package.json`/`tsconfig.json`, `Cargo.toml`, and `go.mod` to detect skills and generate proposals.
4. **AI-Backed Deep Analysis** — LLM-powered theme extraction from recent context snapshots, with budget enforcement, usage logging, and provider fallback.
5. **CLI Command Suite** — Five new `pd dossier` subcommands: `init`, `validate`, `sync-skills`, `sync-tags`, `show`, and `export`.
6. **Rich Terminal UX** — Human-readable layer renderers with skill profile bars, tables, and structured output for all 5 dossier layers.

### 1.2 Files Touched

| File | Type | Lines | Role |
|------|------|-------|------|
| `prime_directive/core/identity.py` | Modified | +766 | 5-layer dossier model, validation, tag normalization, auto-fix |
| `prime_directive/core/empire.py` | **New** | +166 | Empire project config, cycle detection |
| `prime_directive/core/skill_scanner.py` | **New** | +538 | Multi-language scanning, sync proposals, theme extraction |
| `prime_directive/core/dossier_ai.py` | **New** | +289 | AI theme suggestion generation with provider abstraction |
| `prime_directive/bin/pd.py` | Modified | +833 | CLI commands, Rich renderers, orchestration |
| `tests/test_empire.py` | **New** | +112 | Empire config parsing and validation tests |
| `tests/test_skill_scanner.py` | **New** | +449 | Skill scanning, proposals, CLI integration tests |
| `tests/test_identity.py` | Modified | +358 | Layer 2 rendering, export contract tests |
| `tests/test_dossier_ai.py` | **New** | +81 | AI theme generation tests |
| `tests/test_cli.py` | Modified | minor | Config override test cleanup |
| `tests/test_scribe.py` | Modified | -1 | Unused import removal |
| `docs/PD-ARCH-V3.0-GRAND-STRATEGIST.md` | **New** | — | V3.0 architecture documentation |
| `docs/PD-ARCH-V3.1-IDENTITY.md` | **New** | +1950 | V3.1 specification document |

### 1.3 Architectural Boundary

The V3.1 spec (`docs/PD-ARCH-V3.1-IDENTITY.md`) explicitly defines a producer-consumer boundary:

- **Producer:** Prime Directive generates and maintains `operator_dossier.yaml` through CLI commands.
- **Consumer:** External systems (matching engines, portfolio dashboards, CRM integrations) consume the dossier as a structured data artifact.

This branch implements only the **producer side**. The consumer contract is defined by the `pd dossier export` command which outputs JSON, YAML, or tags-only formats. The broader V3.0 portfolio engine (overseer, scoring, renderer) is explicitly out of scope for Phase A.

---

## 2. Architecture & Module Inventory

### 2.1 New Modules

#### 2.1.1 `prime_directive/core/empire.py` (166 lines)

Defines the empire configuration layer — a project-level metadata overlay on top of `config.yaml` repos.

**Data Model:**
- `ProjectRole` — `str` enum: `RESEARCH`, `INFRASTRUCTURE`, `MAINTENANCE`, `EXPERIMENTAL`
- `StrategicWeight` — `str` enum: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
- `EmpireProject` — frozen dataclass: `id`, `domain`, `role`, `strategic_weight`, `description`, `depends_on`
- `EmpireConfig` — frozen dataclass: `version`, `projects` (dict keyed by project ID)
- `WEIGHT_NUMERIC_MAP` — module-level constant mapping `StrategicWeight` → int (1–4), replacing a per-access dict construction (CodeRabbit fix)

**Key Functions:**
- `load_empire_if_exists(cfg, path?)` → `Optional[EmpireConfig]` — returns `None` if `empire.yaml` doesn't exist; never raises for missing file
- `load_empire_config(cfg, path?)` → `EmpireConfig` — raises `ValueError` on parse failure
- `parse_empire_config(raw_data, cfg)` → `EmpireConfig` — validates version (`"3.0"` required), validates project IDs exist in `cfg.repos`, validates enum values with human-readable error messages, validates `depends_on` references, runs cycle detection
- `_find_cycle(projects)` → `list[str]` — DFS-based cycle detection on the dependency graph; returns the cycle path (e.g., `["A", "B", "C", "A"]`) or empty list

**Design Decisions:**
- All dataclasses are `frozen=True` for immutability — appropriate for config objects loaded once.
- `weight_numeric` property uses module-level `WEIGHT_NUMERIC_MAP` instead of creating a dict on every access (post-CodeRabbit optimization).
- Cycle detection uses `[*stack[start:], node]` list unpacking (post-CodeRabbit optimization replacing `stack[start:] + [node]`).
- Empire projects are cross-validated against `config.yaml` repo IDs — a project in `empire.yaml` that doesn't correspond to a configured repo is rejected immediately.

#### 2.1.2 `prime_directive/core/skill_scanner.py` (538 lines)

Handles static analysis of dependency files and generates structured sync proposals.

**Data Model:**
- `DetectedSkill` — frozen dataclass: `skill_name`, `source` (file path), `confidence` (0.0–1.0)
- `RepoScanSummary` — frozen dataclass: `repo_id`, `source_files`, `detected_skills`
- `SyncProposal` — frozen dataclass: `action` (`"add_skill"` | `"add_project"`), `repo_id`, `value_name`, `source`, `confidence`, plus optional project metadata fields (`project_tech_stack`, `project_description`, `project_capability_tags`, `project_url`)
- `ThemeSuggestion` — frozen dataclass: `tag`, `occurrences`, `sample`, `confidence`

**Confidence Tiers:**
- `LANGUAGE_CONFIDENCE = 0.95` — file existence implies language (e.g., `pyproject.toml` → Python)
- `RUNTIME_CONFIDENCE = 0.8` — production dependency listed in manifest
- `DEV_CONFIDENCE = 0.5` — dev/build/optional dependency

**Scanning Coverage:**
| Language | Manifest File | Sections Parsed |
|----------|--------------|-----------------|
| Python | `pyproject.toml` | `project.dependencies`, `project.optional-dependencies.*`, `dependency-groups.*` |
| JavaScript/TypeScript | `package.json` + `tsconfig.json` | `dependencies`, `peerDependencies`, `devDependencies` |
| Rust | `Cargo.toml` | `dependencies`, `build-dependencies`, `dev-dependencies`, `target.*.{deps}` |
| Go | `go.mod` | `require` blocks, inline `require`, `tool` directives |

**Skill Normalization:**
- `SKILL_ALIASES` (8 entries) maps common package names to canonical skill names (e.g., `"@prisma/client"` → `"Prisma"`, `"pyyaml"` → `"PyYAML"`).
- `format_skill_name()` applies alias lookup or returns the raw name. No title-casing, no grouping of related packages.
- Deduplication within a repo uses `(skill_name.lower(), source)` as key, keeping the highest-confidence entry.

**Theme Extraction (Non-AI Path):**
- `build_theme_suggestions(snapshot_texts, existing_tags, limit=5)` — rule-based bigram extraction using `itertools.pairwise` (post-CodeRabbit optimization replacing manual `zip(tokens, tokens[1:])`).
- Filters tokens by length (≥4), removes stop words, counts per-text unique tags, requires ≥2 occurrences across texts.
- Note: This function exists but is **not called from the CLI** — the CLI path uses `generate_theme_suggestions_with_ai` from `dossier_ai.py` instead. The rule-based function serves as a fallback or test utility.

**Proposal Generation:**
- `build_sync_proposals(cfg, dossier)` iterates all `cfg.repos`, scans each, generates `add_skill` proposals for skills not already in the dossier, generates `add_project` proposals for empire-declared projects not already in the dossier.
- Project proposals include enriched metadata: `description` and `capability_tags` from `empire.yaml`, `tech_stack` from scan results.
- `apply_sync_proposals(dossier, proposals)` mutates the dossier in-place, appending new `Skill` and `ProjectBuilt` entries. Returns the same dossier reference.

#### 2.1.3 `prime_directive/core/dossier_ai.py` (289 lines)

Encapsulates AI-backed deep analysis for dossier theme extraction.

**Data Model:**
- `AIAnalysisMetadata` — frozen dataclass: `provider`, `model`, `input_tokens`, `output_tokens`, `cost_estimate_usd`

**Core Function:**
- `generate_theme_suggestions_with_ai(...)` — async function accepting 18+ keyword arguments. Returns `tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]` where the third element is an error message string (not an exception).

**Provider Flow:**
1. If `provider == "openai"`: check API key → check budget → call `generate_openai_chat_with_usage` → parse response → log usage
2. If `provider != "openai"` (default: Ollama): call `generate_ollama` → on success, parse → log; on failure, attempt OpenAI fallback (if configured and confirmed)
3. Fallback path: check `require_confirmation` → check API key → check budget → call OpenAI → parse → log

**Internal Helpers:**
- `_count_tokens(text, model)` — wraps `tiktoken` in double try/except. Returns 0 on any failure (including `ImportError`). Used only for post-call metadata, not pre-call truncation.
- `_extract_json_text(raw_text)` — strips markdown code fences from LLM responses before JSON parsing.
- `_parse_theme_suggestions_response(raw_text, existing_tags, limit)` — parses JSON, filters duplicates and existing tags, normalizes tag format, clamps confidence to [0.0, 1.0], returns up to `limit` suggestions.
- `_log_usage(db_path, ...)` — async wrapper around `log_ai_usage` from `ai_providers.py`; no-ops if `db_path` is falsy.

**Reuse of Existing Infrastructure:**
This module imports and reuses 6 functions from `prime_directive.core.ai_providers`: `check_budget`, `estimate_cost`, `generate_ollama`, `generate_openai_chat_with_usage`, `get_openai_api_key`, `log_ai_usage`. The underlying network calls, budget enforcement, and usage tracking are shared with the existing SITREP generation in `scribe.py`. However, the *orchestration pattern* (primary → fallback → budget check → log) is reimplemented rather than abstracted into a shared utility.

### 2.2 Modified Modules

#### 2.2.1 `prime_directive/core/identity.py` (+766 lines, now 766 total)

The bulk of this file is new content implementing the 5-layer dossier model. Key additions:

- **13 dataclasses** defining the full schema: `Education`, `MilitaryService`, `GeographicEntry`, `Publication`, `HumanIdentity`, `Skill`, `ProjectBuilt`, `Methodology`, `TechnicalCapabilities`, `Company`, `ProfessionalNetwork`, `Offering`, `StrategicPositioning`, `ConnectionSurface`, `OperatorDossier`, `ValidationReport`
- **Validation engine** — `validate_operator_dossier_data()` checks version, skill depth/recency enums, tag normalization, duplicate detection, tag count warnings, tech_stack↔skill cross-referencing, and empty layer detection.
- **Tag normalization** — `normalize_tag()` lowercases, replaces `_` with `-`, collapses multiple hyphens, strips whitespace.
- **Auto-fix system** — `preview_operator_dossier_tag_normalization_fixes()` and `apply_operator_dossier_tag_normalization_fixes()` allow the CLI to offer and apply tag corrections interactively.
- **Connection surface derivation** — `sync_connection_surface()` derives Layer 5 tags from Layers 1–4: experience_tags from military/education/formative_experiences, topic_tags from domain_expertise/publications/projects, geographic/education/industry/hobby tags from respective identity and network fields. Philosophy tags are preserved (never auto-derived).
- **Improved error reporting** (CodeRabbit fix) — `load_operator_dossier()` formats validation errors as a multi-line bulleted list with file path context.

#### 2.2.2 `prime_directive/bin/pd.py` (+833 lines, now 2,140 total)

All new CLI commands and rendering logic are added to this single file:

- **5 dossier subcommands** registered under `dossier_app = typer.Typer()` and mounted via `app.add_typer(dossier_app, name="dossier")`
- **5 layer-specific Rich renderers** (`_print_identity_layer`, `_print_capabilities_layer`, `_print_network_layer`, `_print_positioning_layer`, `_print_connection_surface_layer`)
- **Helper functions** — `_bootstrap_dossier`, `_seed_programming_languages`, `_load_recent_snapshot_texts`, `_render_connection_surface_table`, `_format_skill_profile`
- **New imports** — `click.core.ParameterSource` (for `--apply`/`--dry-run` mutual exclusivity), `generate_theme_suggestions_with_ai`, `load_empire_if_exists`, and 8 identity module functions

### 2.3 Module Dependency Graph

```
pd.py (CLI orchestration)
├── identity.py (data model, validation, I/O)
├── skill_scanner.py (scanning, proposals)
│   ├── identity.py (OperatorDossier, Skill, ProjectBuilt, normalize_tag)
│   └── empire.py (ProjectRole, load_empire_if_exists)
├── dossier_ai.py (AI theme extraction)
│   ├── ai_providers.py (shared AI infrastructure)
│   ├── identity.py (normalize_tag)
│   └── skill_scanner.py (ThemeSuggestion)
└── empire.py (load_empire_if_exists — used in dossier_init)
```

**Notable:** `dossier_ai.py` imports `ThemeSuggestion` from `skill_scanner.py`, creating a dependency from the AI module back to the scanner. This means `dossier_ai.py` cannot be used independently of the scanner module, even though its only dependency on it is a single dataclass.

---

## 3. Feature-by-Feature Analysis

### 3.1 Empire Configuration (`empire.yaml`)

**What it does:** Declares project-level metadata (domain, role, strategic weight, description, inter-project dependencies) that enriches the dossier's `projects_built` entries beyond what static scanning can detect.

**What works well:**
- **Cross-validation with `config.yaml`** — every project ID in `empire.yaml` must exist in `cfg.repos`. This prevents orphaned empire entries and gives clear error messages: `"Empire project 'foo' is not present in config.yaml repos"`.
- **Enum validation with human-readable errors** — invalid `role` or `strategic_weight` values produce messages listing all valid options, not just "invalid value."
- **Dependency cycle detection** — the DFS implementation in `_find_cycle()` correctly identifies cycles and returns the full cycle path for error messages (e.g., `"A -> B -> C -> A"`).
- **Frozen dataclasses** — `EmpireProject` and `EmpireConfig` are immutable, preventing accidental mutation of config objects.

**What could be improved:**
- **No schema version migration** — only `"3.0"` is accepted. There's no forward-compatibility path if the schema needs to evolve. A version range or migration function would be more resilient.
- **`depends_on` is validated but unused** — dependencies are validated (references checked, cycles detected) but nothing in the current branch *uses* the dependency graph for ordering, scoring, or display. The validation is forward-looking infrastructure with no current consumer.
- **No `empire.yaml` generation tooling** — users must hand-author this file. A `pd empire init` command or interactive builder would reduce onboarding friction.

### 3.2 Multi-Language Skill Scanning

**What it does:** Parses dependency manifest files across 4 language ecosystems to detect skills, then generates `add_skill` and `add_project` proposals for dossier enrichment.

**What works well:**
- **Confidence tiering** — the three-tier model (`LANGUAGE_CONFIDENCE=0.95`, `RUNTIME_CONFIDENCE=0.8`, `DEV_CONFIDENCE=0.5`) provides meaningful signal about how certain a skill detection is.
- **Deduplication** — within a repo, `(skill_name.lower(), source)` keying keeps only the highest-confidence entry per skill. Cross-repo deduplication happens at proposal time against the existing dossier.
- **Rust `target.*` handling** — `scan_cargo_toml_dependencies()` correctly handles platform-specific dependencies under `[target.'cfg(...)'.dependencies]`, which many Cargo.toml parsers miss.
- **Go module name extraction** — `_extract_go_module_name()` handles versioned module paths (e.g., `github.com/foo/bar/v3` → `bar`) by detecting trailing `v<N>` segments.
- **TypeScript detection** — presence of `tsconfig.json` alongside `package.json` upgrades the detected language from "JavaScript" to "TypeScript." Simple and effective heuristic.

**What could be improved:**
- **Sparse alias table** — `SKILL_ALIASES` has only 8 entries. A Python project using `requests`, `flask`, `django`, `fastapi`, `sqlalchemy`, `celery`, and `boto3` would generate 7 separate low-value skills. There's no grouping (e.g., "Web Frameworks" for flask/django/fastapi) and no minimum-significance filter.
- **No `requirements.txt` or `setup.py` support** — only `pyproject.toml` is scanned for Python. Legacy projects using `requirements.txt` or `setup.cfg` would produce zero Python dependency detections (though `pyproject.toml` presence still detects "Python" as a language).
- **No `go.sum` or workspace support** — Go workspaces (`go.work`) and `go.sum` are not parsed. Only `go.mod` is supported.
- **No Rust workspace support** — `Cargo.toml` is only checked at the repo root. Rust workspaces with member crates in subdirectories would only detect root-level dependencies.
- **Phantom project proposals** — `build_sync_proposals()` generates `add_project` proposals for empire-declared projects without verifying that `repo_path.exists()`. If `config.yaml` references a repo that's been moved or deleted, `scan_repository()` returns empty results (no files found), but the empire project proposal is still generated with an empty `tech_stack`. This creates phantom project entries in the dossier with no actual backing code.

### 3.3 AI-Backed Deep Analysis

**What it does:** Sends recent context snapshot texts to an LLM (Ollama or OpenAI) to extract recurring technical themes suitable for `capabilities.domain_expertise` tags.

**What works well:**
- **Structured prompt engineering** — the prompt explicitly requests JSON output with a defined schema (`{"suggestions":[{"tag":"...","occurrences":N,"evidence":"...","confidence":0.7}]}`), reducing parsing failures.
- **Budget enforcement** — OpenAI calls check the monthly budget via `check_budget()` before making requests, with human-readable budget-exceeded messages.
- **Usage logging** — both successful and failed AI calls are logged to the database with provider, model, token counts, and cost estimates.
- **Robust response parsing** — `_extract_json_text()` handles markdown code fences, `_parse_theme_suggestions_response()` handles both `{"suggestions":[...]}` and bare `[...]` response formats, normalizes tags, deduplicates against existing dossier tags, and clamps confidence values.
- **Graceful degradation** — all error paths return `([], None, error_message)` rather than raising, so the CLI can display the error and continue with non-AI results.

**What could be improved:**
- **No prompt token budget** — `_load_recent_snapshot_texts()` fetches up to 100 snapshots (each with up to 4 text fields), concatenates them all, and sends the full text to the LLM with no truncation or token budget check. While `_count_tokens()` exists, it's only used *after* the API call for cost accounting, not *before* for prompt size management. A large snapshot corpus could exceed context windows, causing API errors or truncated analysis.
- **Silent token count failures** — `_count_tokens()` returns 0 on any exception, including `ImportError` if `tiktoken` isn't installed. This means `AIAnalysisMetadata.input_tokens`, `output_tokens`, and `cost_estimate_usd` silently report 0 when tiktoken is missing, without any warning. Cost tracking becomes invisible garbage.
- **Errors as strings, not exit codes** — `generate_theme_suggestions_with_ai()` returns errors as the third tuple element (`Optional[str]`). The CLI prints these errors but does NOT set a non-zero exit code. A script calling `pd dossier sync-skills --deep` that encounters a budget exceeded or API error will exit 0, making it invisible to CI/CD pipelines.
- **18+ keyword arguments** — the function signature is extremely wide, passing through every config attribute individually rather than accepting a structured config object. This is a Hydra anti-pattern in a codebase that explicitly values Hydra best practices.
- **No retry/backoff for JSON parse failures** — if the LLM returns malformed JSON (common with smaller models), the error is caught but no retry is attempted. The Ollama path has `max_retries` for network errors but not for response parsing failures.

### 3.4 CLI Command Suite

**What it does:** Provides 6 `pd dossier` subcommands for dossier lifecycle management.

#### 3.4.1 `pd dossier init`
- Creates `~/.prime-directive/operator_dossier.yaml` with auto-populated capabilities.
- Calls `_bootstrap_dossier()` which: creates default dossier → runs `build_sync_proposals` → applies proposals → seeds programming languages → syncs connection surface (Layer 5).
- Prints detailed summary: repo count, empire project count, scanned file count, auto-populated counts, and a "Still needs your input" guide.
- Supports `--force` to overwrite existing dossier.
- **Correctly calls `sync_connection_surface()`** — unlike `sync-skills --apply`.

#### 3.4.2 `pd dossier validate`
- Loads and validates the dossier YAML, reporting errors, warnings, and info.
- **Interactive auto-fix** — detects non-normalized tags, offers to apply fixes via `typer.confirm()`, writes corrected dossier, then re-validates.
- Exits with code 1 if validation fails.

#### 3.4.3 `pd dossier sync-skills`
- Scans repos, generates proposals, optionally runs deep AI analysis.
- `--apply` / `--dry-run` mutual exclusivity uses `click.core.ParameterSource` to detect if `--dry-run` was explicitly passed (since `dry_run=True` is the default). This was a non-trivial Typer/Click integration fix.
- Displays Rich tables for scan summary, proposals, and theme suggestions.
- Reports AI cost when `--deep` is used.
- **Bug: does not call `sync_connection_surface()` after `--apply`** — see Section 5.1.

#### 3.4.4 `pd dossier sync-tags`
- Regenerates Layer 5 connection surface from Layers 1–4.
- Displays before/after tag counts with change deltas.
- Preserves `philosophy_tags` (manual-only field, never auto-derived).

#### 3.4.5 `pd dossier show`
- Human-readable Rich terminal display of all 5 layers.
- `--layer N` shows a single layer (1–5).
- `--tags-only` is a shortcut for `--layer 5`.
- Skill profiles rendered with Unicode progress bars (e.g., `████████░░░ proficient (active)`).

#### 3.4.6 `pd dossier export`
- Structured export for downstream consumption.
- Formats: `json`, `yaml`, `tags-only`.
- `--layer5-only` exports only `version` + `connection_surface`.
- `--output <file>` writes to file; otherwise prints to stdout via `typer.echo()`.
- This is the **consumer contract** — external systems should depend on this output format.

### 3.5 Validation & Auto-Fix System

**What it does:** Validates dossier YAML structure and offers interactive tag normalization.

**What works well:**
- **Multi-level reporting** — `ValidationReport` has `errors` (fatal), `warnings` (non-blocking), and `info` (informational). Only errors cause validation failure.
- **Cross-referencing** — `tech_stack` entries in `projects_built` are checked against the skills list, producing warnings for unmatched entries.
- **Tag normalization consistency** — `normalize_tag()` is used everywhere: validation, auto-fix, connection surface derivation, theme suggestions. Single source of truth for tag format.
- **Safe auto-fix workflow** — preview fixes → user confirms → apply → re-validate. The re-validation step ensures fixes didn't introduce new issues.

**What could be improved:**
- **No schema migration** — if a user has a V3.0 dossier, `validate_operator_dossier_data()` rejects it with `'Invalid dossier version: expected "3.1"'`. There's no `migrate_dossier()` function to upgrade older versions.
- **Tag deduplication is warned, not fixed** — duplicate tags generate warnings but the auto-fix system only handles normalization (case/format), not deduplication. A tag list like `["ml", "ML", "ml"]` would be normalized to `["ml", "ml", "ml"]` — the normalization fix makes it worse by creating exact duplicates from near-duplicates.

### 3.6 Connection Surface Derivation

**What it does:** `sync_connection_surface()` in `identity.py` derives Layer 5 tags deterministically from Layers 1–4.

**Derivation Rules:**
| Layer 5 Field | Source |
|--------------|--------|
| `experience_tags` | Military presence → `"military"`, education/publications → `"research"`, formative experiences keywords → `"career-pivot"`, `"self-taught"`, `"open-source"` |
| `topic_tags` | `domain_expertise` + publication tags + project `capability_tags` + research tags |
| `geographic_tags` | `geographic_history[].location` (comma→space normalization) |
| `education_tags` | `education[].institution` + `education[].field` |
| `industry_tags` | `network.industries` |
| `hobby_tags` | `identity.hobbies` |
| `philosophy_tags` | **Preserved from existing value** — never auto-derived, manual-only |

**Design note:** Philosophy tags are the only field where user-curated values survive a `sync_connection_surface()` call. All other fields are fully regenerated. This is intentional — philosophy is subjective and shouldn't be machine-derived.

---

## 4. Execution Flow Traces

This section traces the concrete control flow for each major user-facing operation, referencing exact file locations. These traces are verified against the source code, not inferred from documentation.

### 4.1 Flow A: `pd dossier init`

```
User runs: pd dossier init [--force]

1. pd.py:dossier_init()
   ├── Check if dossier exists at ~/.prime-directive/operator_dossier.yaml
   │   └── If exists and no --force → exit 1
   ├── Print setup panel (Rich Panel)
   ├── load_config() → DictConfig
   │   ├── Clear GlobalHydra
   │   ├── register_configs()
   │   ├── compose(config_name="config")
   │   ├── Merge user ~/.prime-directive/config.yaml (repos fully replaced)
   │   └── Expand ~ and $ENV in paths
   ├── load_empire_if_exists(cfg)
   │   └── empire.py: check existence → parse → validate → cycle detect
   ├── _bootstrap_dossier(cfg)
   │   ├── default_operator_dossier() → empty OperatorDossier(version="3.1")
   │   ├── build_sync_proposals(cfg, dossier)
   │   │   ├── For each repo in cfg.repos:
   │   │   │   ├── scan_repository(repo_path)
   │   │   │   │   ├── Check pyproject.toml → Python + deps
   │   │   │   │   ├── Check package.json + tsconfig.json → JS/TS + deps
   │   │   │   │   ├── Check Cargo.toml → Rust + deps
   │   │   │   │   └── Check go.mod → Go + deps
   │   │   │   ├── Generate add_skill proposals (skip existing)
   │   │   │   └── Generate add_project proposals (empire-backed only)
   │   │   └── Return (summaries, proposals)
   │   ├── apply_sync_proposals(dossier, proposals) ← mutates dossier
   │   ├── _seed_programming_languages(dossier, summaries)
   │   └── sync_connection_surface(dossier) ← Layer 5 derivation ✓
   ├── write_operator_dossier(dossier, dossier_path)
   │   └── yaml.safe_dump() to file
   └── Print summary (repos, files, skills, projects, languages, tags)
```

**Key observation:** This is the only `--apply`-like path that correctly calls `sync_connection_surface()`.

### 4.2 Flow B: `pd dossier sync-skills --dry-run` (default)

```
User runs: pd dossier sync-skills

1. pd.py:dossier_sync_skills(ctx, apply=False, dry_run=True, deep=False)
   ├── Check ParameterSource for --dry-run (not explicit → no conflict)
   ├── load_config()
   ├── Check dossier exists → exit 1 if not
   ├── load_operator_dossier(dossier_path)
   │   ├── validate_operator_dossier_file(path)
   │   │   └── YAML parse → validate_operator_dossier_data()
   │   ├── If errors → raise ValueError (formatted multi-line)
   │   └── parse_operator_dossier(raw_data) → OperatorDossier
   ├── build_sync_proposals(cfg, dossier)
   ├── Print Rich tables (scan summary, proposals)
   ├── Print summary counts
   └── Print "Dry run only. Re-run with --apply to persist changes."
```

**No side effects.** Dossier file is read but never written.

### 4.3 Flow C: `pd dossier sync-skills --deep --apply`

```
User runs: pd dossier sync-skills --deep --apply

1. pd.py:dossier_sync_skills(ctx, apply=True, dry_run=True, deep=True)
   ├── ParameterSource check: --dry-run not explicit → no conflict
   ├── load_config()
   ├── load_operator_dossier(dossier_path)
   ├── build_sync_proposals(cfg, dossier) → (summaries, proposals)
   ├── Deep analysis path (deep=True):
   │   ├── _load_recent_snapshot_texts(db_path, limit=100)
   │   │   ├── init_db(db_path)
   │   │   ├── Query ContextSnapshot WHERE timestamp >= (now - 30 days)
   │   │   │   ORDER BY timestamp DESC LIMIT 100
   │   │   ├── Extract human_objective, human_blocker, human_next_step, human_note
   │   │   └── Return (texts[], snapshot_count, repo_count)
   │   ├── Read ~15 AI config attributes via getattr(cfg.system, ..., default)
   │   ├── asyncio.run(generate_theme_suggestions_with_ai(...))
   │   │   ├── Join snapshot texts with index prefixes
   │   │   ├── Build structured prompt + system prompt
   │   │   ├── Provider routing:
   │   │   │   ├── If provider=="openai": API key → budget → generate → parse → log
   │   │   │   ├── If provider=="ollama": generate → on fail, try OpenAI fallback
   │   │   │   └── Fallback: confirmation check → API key → budget → generate → parse → log
   │   │   └── Return (suggestions[], metadata?, error?)
   │   └── Build cost display line if metadata present
   ├── Print Rich tables (scan, proposals, theme suggestions)
   ├── Apply path (apply=True):
   │   ├── apply_sync_proposals(dossier, proposals) ← adds skills + projects
   │   ├── _seed_programming_languages(dossier, summaries)
   │   ├── For each theme suggestion: add to domain_expertise (skip existing)
   │   ├── write_operator_dossier(dossier, dossier_path)
   │   └── ⚠️ sync_connection_surface() is NOT called ⚠️
   └── Print "Applied N proposal(s)"
```

**Critical bug:** After applying proposals (which add new skills, projects, and domain expertise tags), the connection surface (Layer 5) is NOT regenerated. Topic tags, for example, derive from `domain_expertise` and `projects_built.capability_tags` — both of which were just modified. The user must manually run `pd dossier sync-tags` afterward to bring Layer 5 into consistency.

### 4.4 Flow D: `pd dossier validate`

```
User runs: pd dossier validate

1. pd.py:dossier_validate()
   ├── validate_operator_dossier_file(dossier_path)
   │   ├── File existence check
   │   ├── YAML parse (yaml.safe_load)
   │   ├── validate_operator_dossier_data(raw_data, report)
   │   │   ├── Version check ("3.1")
   │   │   ├── Skill depth ∈ {expert, proficient, familiar}
   │   │   ├── Skill recency ∈ {active, recent, historical}
   │   │   ├── Tag normalization check (all tag lists)
   │   │   ├── Duplicate tag detection
   │   │   ├── Connection surface tag count warnings (>50)
   │   │   ├── tech_stack ↔ skills cross-reference
   │   │   └── Empty layer detection
   │   └── Return (report, raw_data)
   ├── preview_operator_dossier_tag_normalization_fixes(raw_data)
   │   └── If fixes available:
   │       ├── Print fix preview
   │       ├── typer.confirm("Apply suggested tag normalization fixes?")
   │       ├── If confirmed:
   │       │   ├── apply_operator_dossier_tag_normalization_fixes(raw_data)
   │       │   ├── write_operator_dossier(parse_operator_dossier(raw_data), path)
   │       │   └── Re-validate → fresh (report, raw_data)
   │       └── If declined: continue with original report
   ├── Print errors (red), warnings (yellow), info (blue)
   ├── Print summary: "errors=N warnings=N info=N"
   └── If errors → "Validation failed" + exit 1
       Else → "Validation passed"
```

### 4.5 Flow E: `pd dossier show` / `pd dossier export`

```
User runs: pd dossier show [--layer N] [--tags-only]

1. pd.py:dossier_show()
   ├── load_operator_dossier(dossier_path)
   ├── If --tags-only → _print_connection_surface_layer(dossier) → return
   ├── If --layer N:
   │   ├── Map N → {1:identity, 2:capabilities, 3:network, 4:positioning, 5:connection_surface}
   │   └── Call corresponding _print_*_layer(dossier) → return
   └── If no options: print all 5 layers sequentially

User runs: pd dossier export [--format json|yaml|tags-only] [--output file] [--layer5-only]

1. pd.py:dossier_export()
   ├── load_operator_dossier(dossier_path)
   ├── operator_dossier_to_dict(dossier)
   ├── If --layer5-only → extract {version, connection_surface}
   ├── Format: json.dumps / yaml.safe_dump / tags-only (newline-separated)
   ├── If --output → write to file
   └── Else → typer.echo(payload_text)
```

**Note on `show` vs `export`:** `show` produces Rich-formatted terminal output (tables, progress bars, colors) while `export` produces machine-parseable structured data. They use different rendering paths — `show` calls layer-specific print functions that access dataclass attributes directly, while `export` serializes via `operator_dossier_to_dict()` (which uses `dataclasses.asdict()`).

