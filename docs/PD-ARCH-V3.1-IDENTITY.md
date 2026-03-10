# Prime Directive V3.1 — The Operator Identity Protocol

> **Supplement to:** PD-ARCH-V3.0-GRAND-STRATEGIST.md  
> **Version:** 3.1.0-draft  
> **Date:** 2025-03-08  
> **Status:** Design Specification  
> **Prerequisite:** V3.0 Grand Strategist Protocol (portfolio engine must exist)

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 3.1.0-draft | 2025-03-08 | Initial specification based on systematic critique analysis |

---

## 1. Executive Summary

### 1.1 The Problem

Prime Directive V3.0 (the Grand Strategist) answers: **"What should I work on today?"** It builds a deterministic scoring engine over a project portfolio, producing ranked recommendations based on strategic weight, staleness, dependencies, and deadlines.

V3.0 is entirely blind to a complementary question: **"Who am I, and how does my identity connect to the people and opportunities I want to reach?"**

This gap matters because the operator's daily work — captured by `pd freeze`, scored by `pd overseer` — is continuously building and reshaping a professional identity. That identity, if structured, becomes a strategic asset for:

- **Outreach:** Finding genuine, non-generic connection points with targets (individuals, companies, collaborators).
- **Self-assessment:** Understanding capability gaps, tracking skill evolution, maintaining narrative coherence.
- **Portfolio prioritization feedback:** Choosing which projects to invest in based on which capabilities they build toward strategic goals.

### 1.2 The Solution

V3.1 introduces the **Operator Identity Protocol**: a structured, machine-readable representation of the operator's identity stored at `~/.prime-directive/operator_dossier.yaml`. This file serves as a **shared contract** — written and maintained within Prime Directive, consumed by external systems (notably `black-box`) for outreach automation and intersection scoring.

V3.1 adds:

1. **`operator_dossier.yaml`** — A 5-layer YAML schema capturing the operator's human identity, technical capabilities, professional network, strategic position, and a derived connection surface index.
2. **`pd dossier` command suite** — Commands to view, validate, and partially automate dossier maintenance.
3. **An integration contract** — A formal specification of how external systems (e.g., `black-box`) consume the dossier for `operator ∩ target` intersection scoring.

### 1.3 Scope Boundaries

V3.1 is deliberately narrow. It defines the **data model** and the **maintenance commands**. It does NOT implement:

- **Outreach execution.** The `find-intersections` and SMYKM prompt construction belong in `black-box`, not in Prime Directive. PD produces operator data; black-box consumes it.
- **Target profiling.** V3.1 does not scrape, analyze, or store information about outreach targets. That is black-box's domain.
- **Automated philosophy inference.** LLM-based inference of values and philosophy from project documents is unreliable. V3.1 treats Layer 1 (Human Identity) and Layer 4 (Strategic Position) as primarily manual, with explicit automation boundaries documented.

### 1.4 Design Principles

These principles are inherited from V3.0 (§3) and extended for identity management:

1. **Honesty about automation.** Every field in the dossier is explicitly classified as MANUAL, SEMI-AUTOMATED, or DERIVED. No false promises about "living dossiers" that require the same manual effort as a resume.
2. **Shared contract, not shared codebase.** The dossier YAML file is the integration point between PD and black-box. Neither system imports the other's code. The YAML schema is the API.
3. **Progressive value.** The dossier is useful at every level of completeness. A dossier with only Layer 2 (auto-synced technical skills) is still valuable for capability tracking. Adding Layer 1 (human identity) enables outreach. Adding Layer 5 (connection surface) enables automated intersection scoring.
4. **Additive to V3.0.** V3.1 does not modify any V3.0 file, schema, command, or behavior. It is a pure addition — new files, new commands, new schema. V3.0 works identically with or without V3.1.

---

## 2. Relationship to V3.0

V3.1 is a **supplemental specification**, not a revision. It builds on top of V3.0's data structures and infrastructure without modifying them. This section maps every dependency between the two specs.

### 2.1 What V3.1 Reads from V3.0 (Input Dependencies)

V3.1 consumes the following V3.0 artifacts as **read-only inputs**. V3.1 never writes to, modifies, or extends these structures.

| V3.0 Artifact | What V3.1 Reads | Purpose in V3.1 |
|----------------|-----------------|-----------------|
| `empire.yaml` | `projects[*].domain`, `projects[*].role`, `projects[*].description` | Seed data for Layer 2 (Technical Capability). The `domain` field provides industry/topic tags. The `role` field (RESEARCH, INFRASTRUCTURE, etc.) maps to capability categories. |
| `config.yaml` | `repos[*].path` | Used by `pd dossier sync-skills` to locate project directories and scan their dependency files (`pyproject.toml`, `package.json`, `Cargo.toml`, etc.). |
| `ContextSnapshot` table | `human_objective`, `human_blocker`, `human_note` | Optional enrichment source. When running `pd dossier sync-skills --deep`, the system can scan recent snapshots to extract recurring themes and tag candidates. This is advisory only — the operator confirms or rejects each suggestion. |
| `RepositoryHeartbeat` table | `status`, `summary` | Not directly consumed. Future versions may correlate heartbeat history with skill progression, but V3.1 does not implement this. Listed here for completeness. |
| AI provider infrastructure | `core/ai_providers.py`, `AIUsageLog` | If V3.1 uses the cheap LLM for tag extraction (in `sync-skills --deep`), it reuses the same provider, budget, and logging infrastructure as V3.0 heartbeat generation. |

### 2.2 What V3.1 Adds (New Artifacts)

| Artifact | Type | Path | Description |
|----------|------|------|-------------|
| `operator_dossier.yaml` | Config file | `~/.prime-directive/operator_dossier.yaml` | The 5-layer operator identity schema. Human-editable YAML. |
| `core/identity.py` | Python module | `prime_directive/core/identity.py` | Parser and validator for `operator_dossier.yaml`. Typed dataclasses for all 5 layers. |
| `core/skill_scanner.py` | Python module | `prime_directive/core/skill_scanner.py` | Scans project dependency files across all repos to extract technical skill tags. |
| `pd dossier` | CLI command group | `bin/pd.py` (new command group) | Commands: `show`, `validate`, `sync-skills`, `export`. |
| `tests/test_identity.py` | Test file | `tests/test_identity.py` | Unit tests for dossier parsing, validation, and skill scanning. |

### 2.3 What V3.1 Does NOT Touch

The following V3.0 components are completely untouched by V3.1:

| Component | Reason |
|-----------|--------|
| `pd overseer` pipeline (all 6 stages) | Identity data does not feed into project scoring. V3.0's scoring is purely based on portfolio state, not operator identity. |
| `empire.yaml` schema | V3.1 reads `empire.yaml` but never writes to it or extends its schema. |
| `strategy.md` format | V3.1 does not consume or modify strategy documents. |
| `RepositoryHeartbeat` table | V3.1 does not add columns or modify the heartbeat schema. |
| `core/scoring.py` | Scoring weights and factors are unchanged. |
| `core/overseer.py` | The pipeline orchestrator is unchanged. |
| `core/renderer.py` | The overseer report format is unchanged. |
| All V1.x components | Freeze, switch, SITREP, metrics, daemon — all unchanged. |

### 2.4 Architectural Boundary

The relationship between V3.0 and V3.1 is **producer-consumer**, not **bidirectional**.

```
V3.0 (Portfolio Engine)                    V3.1 (Identity Protocol)
─────────────────────                      ────────────────────────

empire.yaml ──────────────────read────────→ skill tag seeding
config.yaml ──────────────────read────────→ repo path discovery
ContextSnapshot ──────────────read────────→ theme extraction (optional)
ai_providers.py ──────────────reuse───────→ LLM calls for tag extraction

                                            operator_dossier.yaml
                                                     │
                                                     │ read (external)
                                                     ▼
                                            black-box outreach system
```

V3.1 never writes back to V3.0 artifacts. V3.0 never reads `operator_dossier.yaml`. The two specs share infrastructure (AI providers, database engine, CLI framework) but not data flow in the reverse direction.

**One potential future exception** (explicitly out of scope for V3.1): A future V3.2 could add a scoring factor to `pd overseer` that considers which projects build toward capability gaps identified in the dossier. This would create a feedback loop where identity awareness influences portfolio prioritization. This is noted in §7 (Strategic Flywheel) but is not implemented in V3.1.

---

## 3. The `operator_dossier.yaml` Schema

The dossier is stored at `~/.prime-directive/operator_dossier.yaml`. It is a single, human-editable YAML file organized into 5 layers. Each layer has a distinct purpose and a distinct automation profile (detailed in §4).

### 3.1 Schema Overview

```yaml
# ~/.prime-directive/operator_dossier.yaml
# Prime Directive V3.1 — Operator Identity Protocol
version: "3.1"

# Layer 1: Who you are as a human
identity:
  # ...

# Layer 2: What you can build
capabilities:
  # ...

# Layer 3: Who knows you and can vouch
network:
  # ...

# Layer 4: What you offer and how you position yourself
positioning:
  # ...

# Layer 5: Machine-readable tags for intersection scoring
connection_surface:
  # ...
```

### 3.2 Layer 1: Human Identity

**Purpose:** Capture the properties of the operator that enable genuine human connection — shared experiences, values, and background that go beyond technical skills.

**Automation class:** MANUAL. This layer is populated entirely by the operator. No automated scanning or LLM inference.

**Rationale for manual-only:** LLM inference of values from project documents is unreliable and hallucinatory. The statement "Always test against staging" does not reliably map to `craft-over-speed` — an LLM might equally infer `risk-averse` or `ops-heavy`. Philosophy and identity must be human-authored to be authentic.

```yaml
identity:
  # Formal education history
  education:
    - institution: "University of Example"
      degree: "B.S. Computer Science"
      field: "Artificial Intelligence"
      years: "2015-2019"
      notable: "Research assistant, NLP lab under Dr. Smith"

  # Military or government service
  military:
    branch: "US Navy"
    rate_mos: "ETN - Electronics Technician, Nuclear"
    specialty: "Nuclear reactor instrumentation and control"
    clearance: "Secret"
    years: "2010-2015"
    stations:
      - "USS Example (CVN-XX)"
      - "NPTU Charleston"
    deployments:
      - "Western Pacific 2013"

  # Geographic history (enables "I lived there too" connections)
  geographic_history:
    - location: "Charleston, SC"
      years: "2010-2013"
    - location: "San Francisco, CA"
      years: "2016-present"

  # Spoken and programming languages
  languages:
    spoken: ["English", "Spanish (conversational)"]
    programming: ["Python", "TypeScript", "Rust", "SQL"]

  # Hobbies and physical pursuits
  hobbies:
    - "Long-distance backpacking"
    - "Competitive chess"
    - "Technical writing"
    - "Open-source contribution"

  # Formative experiences — career pivots, hardships, defining moments
  formative_experiences:
    - "Transitioned from nuclear engineering to software development"
    - "Built first production system during military service with zero formal CS training"
    - "Open-sourced a side project that gained 500+ stars"

  # Books, authors, frameworks that shaped your worldview
  intellectual_influences:
    - "Nassim Taleb — Antifragile systems thinking"
    - "John Boyd — OODA loop, competitive tempo"
    - "Rich Hickey — Simplicity and decomplection"
    - "Cal Newport — Deep work and craft-over-speed"

  # Public writing and speaking with topic tags
  publications:
    - title: "Compositional Generalization Gaps in Transformer Architectures"
      venue: "arXiv:2512.07109"
      year: 2025
      tags: ["compositional-gap", "transformer-failure-modes", "abstract-reasoning"]
    - title: "Building Trustworthy AI Auditing Pipelines"
      venue: "Personal blog"
      year: 2025
      tags: ["verification", "code-quality", "AI-safety"]

  # Stated beliefs about craft, ownership, systems thinking
  values:
    - "Verification over trust — prove it works, don't assume"
    - "Ownership mentality — if it's broken, it's my problem"
    - "Systems thinking — local optimizations create global problems"
    - "Craft over speed — quality compounds, shortcuts decay"
    - "Anti-hype — substance over narrative"
```

**Validation rules:**
- `version` must be `"3.1"`.
- All fields are optional. An empty `identity` section is valid.
- `geographic_history[*].location` should be a recognizable place name (city, state/country). No strict geocoding validation — free text.
- `publications[*].tags` must be lowercase, hyphenated strings (normalized for intersection matching).
- `values` entries are free-text strings. They are NOT used for automated matching — they are human-readable context for outreach composition. The machine-readable version lives in Layer 5 (`connection_surface.philosophy_tags`).

### 3.3 Layer 2: Technical Capability Inventory

**Purpose:** Enumerate the operator's technical skills, domain expertise, projects, methodologies, and auditable evidence of competence. This is the layer with the highest automation potential.

**Automation class:** SEMI-AUTOMATED. `pd dossier sync-skills` can populate `skills` and `projects_built` by scanning repo dependency files. Everything else is manual.

```yaml
capabilities:
  # Technical skills with self-assessed depth and recency
  # depth: expert | proficient | familiar
  # recency: active | recent | historical
  skills:
    - name: "Python"
      depth: "expert"
      recency: "active"
      evidence: "Primary language across 4 active projects"
    - name: "asyncio"
      depth: "proficient"
      recency: "active"
      evidence: "Refactored prime-directive to fully async I/O"
    - name: "PyTorch"
      depth: "proficient"
      recency: "active"
      evidence: "RNA structure prediction model (rna-predict)"
    - name: "TypeScript"
      depth: "proficient"
      recency: "active"
      evidence: "Next.js application (black-box)"
    - name: "SQLite / SQLModel"
      depth: "proficient"
      recency: "active"
      evidence: "Async SQLModel with WAL mode in prime-directive"
    - name: "Docker / Containerization"
      depth: "familiar"
      recency: "recent"
      evidence: "Containerfile for prime-directive"

  # Domain expertise — tagged for intersection matching
  domain_expertise:
    - "forensic-auditing"
    - "verification-systems"
    - "ML-pipeline"
    - "environmental-data"
    - "nuclear-electronics"
    - "developer-tooling"
    - "AST-mutation-testing"
    - "agent-safety"

  # Published research with connection-surface tags
  # (Mirrors identity.publications but focuses on technical content)
  research:
    - title: "Compositional Generalization Gaps in Transformer Architectures"
      arxiv: "2512.07109"
      key_findings:
        - "Identified systematic failure modes in compositional reasoning"
        - "Proposed diagnostic benchmark for abstract pattern generalization"
      tags: ["compositional-gap", "transformer-failure-modes", "abstract-reasoning"]

  # Projects built — each with tech stack and capability tags
  # This section can be auto-populated by `pd dossier sync-skills`
  projects_built:
    - name: "prime-directive"
      url: "https://github.com/ImmortalDemonGod/prime-directive"
      description: "CLI tool for multi-project context preservation and portfolio management"
      tech_stack: ["Python", "Typer", "SQLModel", "Hydra", "Rich", "asyncio"]
      capability_tags: ["developer-tooling", "CLI-design", "async-python", "AI-integration"]
    - name: "rna-predict"
      url: null
      description: "RNA 3D structure prediction using AlphaFold 3-inspired architecture"
      tech_stack: ["Python", "PyTorch", "Hydra", "pytest"]
      capability_tags: ["ML-pipeline", "structural-biology", "diffusion-models"]
    - name: "black-box"
      url: null
      description: "Strategic outreach and intelligence platform"
      tech_stack: ["TypeScript", "Next.js", "Prisma", "PostgreSQL"]
      capability_tags: ["full-stack", "outreach-automation", "intelligence-systems"]

  # Methodologies developed — named processes with evidence
  methodologies:
    - name: "AIV Protocol"
      description: "AI-Integrated Verification — systematic protocol for verifying AI-generated claims against source code"
      applicable_contexts: ["code-audit", "due-diligence", "AI-safety"]
      evidence: "docs/AIV-SOP.md in prime-directive"
    - name: "SVP Protocol"
      description: "Sovereign Verification Protocol — independent validation of system claims"
      applicable_contexts: ["technical-due-diligence", "forensic-auditing"]
      evidence: "Applied to 3+ target audits in black-box"

  # Completed audits with depth tier and key findings
  audit_portfolio:
    - target: "Example Corp API"
      depth_tier: "deep"
      key_findings:
        - "Race condition in payment processing pipeline"
        - "Unvalidated deserialization in webhook handler"
      proven: "Identified critical vulnerability before production incident"
```

**Validation rules:**
- `skills[*].depth` must be one of: `expert`, `proficient`, `familiar`.
- `skills[*].recency` must be one of: `active`, `recent`, `historical`.
- `domain_expertise` entries must be lowercase, hyphenated strings.
- `projects_built[*].capability_tags` must be lowercase, hyphenated strings.
- `projects_built[*].tech_stack` entries should match `skills[*].name` where applicable (cross-validation warning if a tech_stack entry has no corresponding skill).

### 3.4 Layer 3: Professional Network & Social Proof

**Purpose:** Capture the operator's professional graph — who can vouch for them, what institutions they've been part of, and what shared affiliations enable warm introductions.

**Automation class:** MANUAL. Professional history and relationships require human input.

```yaml
network:
  # Employment history with accomplishments
  companies:
    - name: "US Navy"
      role: "Electronics Technician, Nuclear"
      years: "2010-2015"
      accomplishment: "Maintained reactor instrumentation systems with 100% operational availability"
    - name: "Startup X"
      role: "Senior Software Engineer"
      years: "2019-2022"
      accomplishment: "Built real-time data pipeline processing 50M events/day"

  # Industries operated in — tagged for matching
  industries:
    - "defense"
    - "AI-agents"
    - "devtools"
    - "environmental"
    - "fintech"

  # Attributed quotes with context
  testimonials:
    - quote: "The most rigorous engineer I've worked with."
      attribution: "CTO, Startup X"
      context: "Performance review, 2021"

  # Professional communities and contributions
  communities:
    - name: "Python Software Foundation"
      role: "Member"
    - name: "Local ML Meetup"
      role: "Occasional speaker"

  # People who can vouch, with relationship context
  collaborators:
    - name: "Dr. Jane Smith"
      relationship: "Research advisor, NLP lab"
      can_vouch_for: ["ML research", "technical writing"]

  # Shared institutional overlaps that create instant affinity
  institutional_overlaps:
    - type: "military_branch"
      value: "US Navy"
    - type: "university"
      value: "University of Example"
    - type: "open_source_project"
      value: "Typer (contributor)"
```

### 3.5 Layer 4: Strategic Position & Offerings

**Purpose:** Define what the operator offers professionally — products, services, positioning, and competitive differentiation. This layer bridges identity to business.

**Automation class:** MANUAL. Business positioning is a strategic decision, not a data extraction task.

```yaml
positioning:
  # One-sentence identity
  positioning_statement: >-
    Forensic technical due diligence for Series A+ infrastructure —
    I find what your existing auditors miss.

  # What makes you different from alternatives
  competitive_differentiation:
    - "Military-grade verification methodology (AIV/SVP protocols)"
    - "Can audit at code level, not just architecture diagrams"
    - "Published research on AI failure modes — not just a practitioner, but a researcher"

  # Product/service catalog
  offerings:
    - name: "Deep Technical Audit"
      description: "Full codebase review with verified findings report"
      deliverable: "Findings document with reproduction steps"
      typical_timeline: "2-4 weeks"
    - name: "Architecture Review"
      description: "High-level architecture and infrastructure assessment"
      deliverable: "Risk assessment with prioritized recommendations"
      typical_timeline: "1 week"

  # Active engagements (proves execution, not just pitching)
  active_engagements:
    - client: "Confidential"
      type: "Deep Technical Audit"
      status: "in_progress"

  # Case studies with measurable outcomes
  case_studies:
    - title: "Payment Pipeline Race Condition Discovery"
      outcome: "Identified critical vulnerability before production incident, saving estimated $2M in potential losses"
      methodology_used: "SVP Protocol"

  # Revenue model
  revenue_model: "Project-based engagements with retainer option for ongoing monitoring"
```

### 3.6 Layer 5: Connection Surface Index

**Purpose:** Machine-readable, normalized tags derived from Layers 1–4. This is the layer that external systems (black-box) consume for automated `operator ∩ target` intersection scoring.

**Automation class:** DERIVED. Generated by `pd dossier sync-tags` from the contents of Layers 1–4. The operator reviews and confirms the derived tags.

```yaml
connection_surface:
  # Derived from identity.military, identity.education, identity.formative_experiences
  experience_tags:
    - "military"
    - "career-pivot"
    - "self-taught"
    - "research"
    - "open-source"

  # Derived from capabilities.domain_expertise, capabilities.projects_built[*].capability_tags
  topic_tags:
    - "verification"
    - "forensic-auditing"
    - "ML-pipeline"
    - "developer-tooling"
    - "async-python"
    - "diffusion-models"
    - "compositional-gap"
    - "agent-safety"
    - "code-quality"

  # Derived from identity.geographic_history
  geographic_tags:
    - "charleston-sc"
    - "san-francisco-ca"

  # Derived from identity.education
  education_tags:
    - "university-of-example"
    - "computer-science"
    - "artificial-intelligence"

  # Derived from network.industries
  industry_tags:
    - "defense"
    - "AI-agents"
    - "devtools"
    - "environmental"
    - "fintech"

  # Derived from identity.hobbies
  hobby_tags:
    - "backpacking"
    - "chess"
    - "technical-writing"
    - "open-source"

  # Derived from identity.values — human-curated keyword distillation
  philosophy_tags:
    - "verification-over-trust"
    - "ownership"
    - "systems-thinking"
    - "craft-over-speed"
    - "anti-hype"
```

**Normalization rules for all tags:**
- Lowercase.
- Hyphenated (no spaces, no underscores).
- No duplicates within a category.
- Maximum 50 tags per category (prevents tag explosion).
- Tags should be specific enough to be discriminating but general enough to match. `"python"` is too broad; `"async-python-sqlite-wal"` is too narrow. `"async-python"` is the right level.

### 3.7 Python Dataclass Representation

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Education:
    institution: str
    degree: str
    field: str
    years: str
    notable: Optional[str] = None

@dataclass
class MilitaryService:
    branch: str
    rate_mos: str
    specialty: str
    clearance: Optional[str] = None
    years: str = ""
    stations: list[str] = field(default_factory=list)
    deployments: list[str] = field(default_factory=list)

@dataclass
class GeographicEntry:
    location: str
    years: str

@dataclass
class Publication:
    title: str
    venue: str
    year: int
    tags: list[str] = field(default_factory=list)

@dataclass
class HumanIdentity:
    education: list[Education] = field(default_factory=list)
    military: Optional[MilitaryService] = None
    geographic_history: list[GeographicEntry] = field(default_factory=list)
    languages: dict[str, list[str]] = field(default_factory=dict)
    hobbies: list[str] = field(default_factory=list)
    formative_experiences: list[str] = field(default_factory=list)
    intellectual_influences: list[str] = field(default_factory=list)
    publications: list[Publication] = field(default_factory=list)
    values: list[str] = field(default_factory=list)


@dataclass
class Skill:
    name: str
    depth: str       # "expert" | "proficient" | "familiar"
    recency: str     # "active" | "recent" | "historical"
    evidence: str = ""

@dataclass
class ProjectBuilt:
    name: str
    description: str
    tech_stack: list[str] = field(default_factory=list)
    capability_tags: list[str] = field(default_factory=list)
    url: Optional[str] = None

@dataclass
class Methodology:
    name: str
    description: str
    applicable_contexts: list[str] = field(default_factory=list)
    evidence: str = ""

@dataclass
class TechnicalCapabilities:
    skills: list[Skill] = field(default_factory=list)
    domain_expertise: list[str] = field(default_factory=list)
    research: list[dict] = field(default_factory=list)
    projects_built: list[ProjectBuilt] = field(default_factory=list)
    methodologies: list[Methodology] = field(default_factory=list)
    audit_portfolio: list[dict] = field(default_factory=list)


@dataclass
class Company:
    name: str
    role: str
    years: str
    accomplishment: str = ""

@dataclass
class ProfessionalNetwork:
    companies: list[Company] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    testimonials: list[dict] = field(default_factory=list)
    communities: list[dict] = field(default_factory=list)
    collaborators: list[dict] = field(default_factory=list)
    institutional_overlaps: list[dict] = field(default_factory=list)


@dataclass
class Offering:
    name: str
    description: str
    deliverable: str = ""
    typical_timeline: str = ""

@dataclass
class StrategicPositioning:
    positioning_statement: str = ""
    competitive_differentiation: list[str] = field(default_factory=list)
    offerings: list[Offering] = field(default_factory=list)
    active_engagements: list[dict] = field(default_factory=list)
    case_studies: list[dict] = field(default_factory=list)
    revenue_model: str = ""


@dataclass
class ConnectionSurface:
    experience_tags: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    geographic_tags: list[str] = field(default_factory=list)
    education_tags: list[str] = field(default_factory=list)
    industry_tags: list[str] = field(default_factory=list)
    hobby_tags: list[str] = field(default_factory=list)
    philosophy_tags: list[str] = field(default_factory=list)


@dataclass
class OperatorDossier:
    version: str
    identity: HumanIdentity = field(default_factory=HumanIdentity)
    capabilities: TechnicalCapabilities = field(default_factory=TechnicalCapabilities)
    network: ProfessionalNetwork = field(default_factory=ProfessionalNetwork)
    positioning: StrategicPositioning = field(default_factory=StrategicPositioning)
    connection_surface: ConnectionSurface = field(default_factory=ConnectionSurface)
```

---

## 4. Automation Analysis

This section provides an honest, field-by-field classification of what can be automated, what requires human input, and what is derived. This is the core differentiator between V3.1 and vaporware — we make no false promises about "living dossiers" that secretly require the same manual effort as writing a resume from scratch.

### 4.1 Automation Classification Legend

| Class | Meaning | Operator Effort |
|-------|---------|----------------|
| **MANUAL** | The operator writes this by hand. No tooling assists. | High — but one-time, with infrequent updates. |
| **SEMI-AUTOMATED** | Tooling proposes values; the operator confirms, rejects, or edits. | Low — review a diff, accept/reject. |
| **DERIVED** | Computed deterministically from other fields. Operator reviews but rarely edits. | Minimal — run a command, glance at output. |

### 4.2 Field-by-Field Classification

#### Layer 1: Human Identity — **95% MANUAL**

| Field | Class | Automation Mechanism | Update Frequency |
|-------|-------|---------------------|-----------------|
| `education` | MANUAL | None. Operator types this once. | Rarely (new degree, certification). |
| `military` | MANUAL | None. | Never (historical record). |
| `geographic_history` | MANUAL | None. | When you move. |
| `languages.spoken` | MANUAL | None. | Rarely. |
| `languages.programming` | SEMI-AUTOMATED | `sync-skills` can detect languages from file extensions across repos and suggest additions. | When you start using a new language. |
| `hobbies` | MANUAL | None. | When interests change. |
| `formative_experiences` | MANUAL | None. | When you have a new defining experience. |
| `intellectual_influences` | MANUAL | None. | When you encounter a new formative work. |
| `publications` | MANUAL | None. Future: could scrape arXiv/ORCID. | When you publish. |
| `values` | MANUAL | None. Explicitly not LLM-inferred (see §3.2 rationale). | When your philosophy evolves. |

**Realistic effort:** 30–60 minutes to populate initially. 5 minutes per quarter to update.

#### Layer 2: Technical Capabilities — **50% SEMI-AUTOMATED**

| Field | Class | Automation Mechanism | Update Frequency |
|-------|-------|---------------------|-----------------|
| `skills` | SEMI-AUTOMATED | `sync-skills` scans `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` across all repos in `config.yaml`. Proposes new skills with `depth: "familiar"` and `recency: "active"`. Operator adjusts depth and adds evidence. | After adding new repos or major dependency changes. |
| `domain_expertise` | MANUAL | Operator curates. Too abstract for automated inference. | When entering a new domain. |
| `research` | MANUAL | Operator adds. Future: arXiv API integration. | When publishing. |
| `projects_built` | SEMI-AUTOMATED | `sync-skills` reads `empire.yaml` projects and `config.yaml` repos. For each, it reads the project's dependency files to auto-populate `tech_stack`. The operator writes `description` and `capability_tags`. | When empire.yaml changes. |
| `methodologies` | MANUAL | Too nuanced for automation. | When developing a new methodology. |
| `audit_portfolio` | MANUAL | Operator curates. Sensitive data — must be human-controlled. | After completing an audit. |

**Realistic effort:** 20 minutes initial (most auto-populated). 10 minutes per month to review `sync-skills` suggestions.

#### Layer 3: Professional Network — **100% MANUAL**

| Field | Class | Automation Mechanism | Update Frequency |
|-------|-------|---------------------|-----------------|
| `companies` | MANUAL | None. | When changing jobs. |
| `industries` | MANUAL | None. | When entering a new industry. |
| `testimonials` | MANUAL | None. | When receiving notable feedback. |
| `communities` | MANUAL | None. | When joining/leaving. |
| `collaborators` | MANUAL | None. | When forming new key relationships. |
| `institutional_overlaps` | MANUAL | None. | Rarely changes. |

**Realistic effort:** 20 minutes initial. Near-zero ongoing unless career changes.

#### Layer 4: Strategic Positioning — **100% MANUAL**

| Field | Class | Automation Mechanism | Update Frequency |
|-------|-------|---------------------|-----------------|
| `positioning_statement` | MANUAL | None. Strategic decision. | When repositioning. |
| `competitive_differentiation` | MANUAL | None. | When adding new differentiators. |
| `offerings` | MANUAL | None. | When product/service catalog changes. |
| `active_engagements` | MANUAL | None. Sensitive. | When engagements start/end. |
| `case_studies` | MANUAL | None. | After completing noteworthy work. |
| `revenue_model` | MANUAL | None. | When business model changes. |

**Realistic effort:** 15 minutes initial. 5 minutes per quarter.

#### Layer 5: Connection Surface Index — **90% DERIVED**

| Field | Class | Source | Derivation Logic |
|-------|-------|--------|-----------------|
| `experience_tags` | DERIVED | Layer 1 | `military` present → `"military"` tag. `formative_experiences` containing "pivot" → `"career-pivot"`. Keywords extracted by simple pattern matching, not LLM. |
| `topic_tags` | DERIVED | Layer 2 | Union of `domain_expertise` + all `capability_tags` from `projects_built` + all `tags` from `research`. Deduplicated. |
| `geographic_tags` | DERIVED | Layer 1 | `geographic_history[*].location` normalized to `"city-state"` lowercase hyphenated format. |
| `education_tags` | DERIVED | Layer 1 | `education[*].institution` + `education[*].field` normalized. |
| `industry_tags` | DERIVED | Layer 3 | Direct copy of `network.industries`. |
| `hobby_tags` | DERIVED | Layer 1 | `hobbies` normalized to lowercase hyphenated. |
| `philosophy_tags` | MANUAL | Layer 1 | Operator distills `values` (free text) into keyword tags. This step is intentionally manual because free-text-to-keyword mapping is lossy and personal. |

**Realistic effort:** Run `pd dossier sync-tags`, review output, manually add `philosophy_tags`. 5 minutes.

### 4.3 Total Effort Summary

| Phase | Estimated Time | Automation Rate |
|-------|---------------|----------------|
| **Initial population** | ~90 minutes | ~25% automated |
| **Monthly maintenance** | ~15 minutes | ~60% automated (sync-skills + sync-tags handle bulk) |
| **Per-project addition** | ~5 minutes | ~80% automated (sync-skills auto-detects new repos) |

### 4.4 The `sync-skills` Algorithm

This is the primary automation mechanism. It is deliberately conservative — it only proposes additions, never deletions. The operator always has final say.

```python
async def sync_skills(cfg: DictConfig, dossier: OperatorDossier) -> list[SyncProposal]:
    """
    Scan all repos in config.yaml for dependency files.
    Compare discovered dependencies against dossier.capabilities.skills.
    Return a list of proposed additions/updates.
    """
    proposals = []
    existing_skill_names = {s.name.lower() for s in dossier.capabilities.skills}

    for repo_id, repo_cfg in cfg.repos.items():
        repo_path = os.path.expanduser(repo_cfg.path)

        # Scan known dependency file formats
        for scanner in [
            scan_pyproject_toml,    # Python: pyproject.toml, setup.cfg, requirements.txt
            scan_package_json,      # JavaScript/TypeScript: package.json
            scan_cargo_toml,        # Rust: Cargo.toml
            scan_go_mod,            # Go: go.mod
        ]:
            detected = scanner(repo_path)
            for dep_name, dep_category in detected:
                normalized = dep_name.lower()
                if normalized not in existing_skill_names:
                    proposals.append(SyncProposal(
                        action="add_skill",
                        field="capabilities.skills",
                        proposed_value=Skill(
                            name=dep_name,
                            depth="familiar",  # Conservative default
                            recency="active",
                            evidence=f"Detected in {repo_id}/{scanner.filename}",
                        ),
                        source=f"{repo_id}/{scanner.filename}",
                        confidence=0.8,
                    ))

    # Also propose projects_built entries for repos in empire.yaml
    # that aren't already in dossier.capabilities.projects_built
    existing_projects = {p.name.lower() for p in dossier.capabilities.projects_built}
    empire = load_empire_if_exists(cfg)
    if empire:
        for pid, project in empire.projects.items():
            if pid.lower() not in existing_projects:
                proposals.append(SyncProposal(
                    action="add_project",
                    field="capabilities.projects_built",
                    proposed_value=ProjectBuilt(
                        name=pid,
                        description=project.description,
                        tech_stack=[],  # Filled by dependency scan
                        capability_tags=[],  # Operator fills
                    ),
                    source="empire.yaml",
                    confidence=0.9,
                ))

    return proposals
```

**Key design decisions:**
- **Conservative depth default.** New skills are proposed as `"familiar"`, not `"proficient"` or `"expert"`. The operator upgrades depth based on their honest self-assessment.
- **No deletions.** If a dependency is removed from a `pyproject.toml`, the corresponding skill is NOT removed from the dossier. Skills persist — you don't "unlearn" Python because you removed it from one project.
- **Source attribution.** Every proposal includes the file and repo that triggered it, so the operator can evaluate whether the detection is meaningful (e.g., a transitive dependency vs. a core framework).
- **Confidence score.** Direct dependencies (listed in `[project.dependencies]`) get `confidence=0.8`. Dev dependencies (listed in `[project.optional-dependencies]`) get `confidence=0.5`. This helps the operator prioritize which proposals to review.

### 4.5 The `sync-tags` Algorithm

This is the derivation mechanism for Layer 5.

```python
def sync_tags(dossier: OperatorDossier) -> ConnectionSurface:
    """
    Derive Layer 5 (ConnectionSurface) from Layers 1-4.
    Returns a new ConnectionSurface with all derived tags.
    philosophy_tags are preserved from the existing surface (manual).
    """
    surface = ConnectionSurface()

    # experience_tags: from Layer 1
    if dossier.identity.military:
        surface.experience_tags.append("military")
    if dossier.identity.education:
        surface.experience_tags.append("research")
    for exp in dossier.identity.formative_experiences:
        exp_lower = exp.lower()
        if "pivot" in exp_lower or "transition" in exp_lower:
            surface.experience_tags.append("career-pivot")
        if "self-taught" in exp_lower or "no formal" in exp_lower:
            surface.experience_tags.append("self-taught")
        if "open-source" in exp_lower or "open source" in exp_lower:
            surface.experience_tags.append("open-source")

    # topic_tags: from Layer 2
    surface.topic_tags = list(set(
        dossier.capabilities.domain_expertise
        + [tag for p in dossier.capabilities.projects_built for tag in p.capability_tags]
        + [tag for r in dossier.capabilities.research for tag in r.get("tags", [])]
    ))

    # geographic_tags: from Layer 1
    for geo in dossier.identity.geographic_history:
        normalized = geo.location.lower().replace(" ", "-").replace(",", "")
        surface.geographic_tags.append(normalized)

    # education_tags: from Layer 1
    for edu in dossier.identity.education:
        surface.education_tags.append(
            edu.institution.lower().replace(" ", "-")
        )
        surface.education_tags.append(
            edu.field.lower().replace(" ", "-")
        )

    # industry_tags: direct copy from Layer 3
    surface.industry_tags = list(dossier.network.industries)

    # hobby_tags: from Layer 1
    surface.hobby_tags = [
        h.lower().replace(" ", "-") for h in dossier.identity.hobbies
    ]

    # philosophy_tags: PRESERVE existing (manual)
    surface.philosophy_tags = dossier.connection_surface.philosophy_tags

    # Deduplicate all tag lists
    for field_name in [
        "experience_tags", "topic_tags", "geographic_tags",
        "education_tags", "industry_tags", "hobby_tags",
    ]:
        tags = getattr(surface, field_name)
        setattr(surface, field_name, sorted(set(tags)))

    return surface
```

---

## 5. The `pd dossier` Command Suite

V3.1 adds a new Typer command group (`pd dossier`) to the existing CLI. All commands operate on `~/.prime-directive/operator_dossier.yaml` and are read-only with respect to all other Prime Directive data (database, empire.yaml, config.yaml).

### 5.1 Command Overview

```
pd dossier <COMMAND> [OPTIONS]

Commands:
  show          Display the dossier in formatted terminal output
  validate      Parse and validate the dossier, reporting errors and warnings
  sync-skills   Scan repos for dependencies and propose skill/project updates
  sync-tags     Derive Layer 5 (connection_surface) from Layers 1-4
  export        Export the dossier in a format consumable by external systems
  init          Generate a skeleton operator_dossier.yaml with guided prompts
```

### 5.2 `pd dossier init`

**Purpose:** Generate a skeleton `operator_dossier.yaml` if one does not exist. Analogous to V3.0's `pd overseer` onboarding wizard (V3.0 §9.2.1).

**Behavior:**

```
$ pd dossier init

╭──────────────────────────────────────────────────────────╮
│  🛡️  PRIME DIRECTIVE — Operator Dossier Setup            │
│                                                          │
│  This will create ~/.prime-directive/operator_dossier.yaml│
│  with a skeleton structure for you to fill in.           │
╰──────────────────────────────────────────────────────────╯

Pre-populating from your project portfolio...
  Found 4 repos in config.yaml
  Found 4 projects in empire.yaml
  Scanned dependency files across all repos

Skeleton written to ~/.prime-directive/operator_dossier.yaml

Auto-populated:
  ✅ capabilities.projects_built: 4 projects from empire.yaml
  ✅ capabilities.skills: 12 dependencies detected across repos
  ✅ connection_surface.topic_tags: 8 tags derived

Still needs your input:
  ⚠️  identity (education, military, hobbies, values, etc.)
  ⚠️  network (companies, industries, collaborators)
  ⚠️  positioning (statement, offerings, case studies)
  ⚠️  connection_surface.philosophy_tags (manual only)

💡 Run 'pd dossier validate' after editing to check for errors.
```

**Implementation:**

```python
@dossier_app.command("init")
def dossier_init():
    """Generate a skeleton operator_dossier.yaml."""
    dossier_path = os.path.expanduser("~/.prime-directive/operator_dossier.yaml")
    if os.path.exists(dossier_path):
        console.print(
            f"[yellow]Dossier already exists at {dossier_path}.[/yellow]\n"
            "Use 'pd dossier sync-skills' to update, or delete the file to regenerate."
        )
        raise typer.Exit(code=1)

    cfg = load_config()

    # Build skeleton with auto-populated Layer 2 and Layer 5
    skeleton = OperatorDossier(version="3.1")
    proposals = asyncio.run(sync_skills(cfg, skeleton))
    for p in proposals:
        if p.action == "add_skill":
            skeleton.capabilities.skills.append(p.proposed_value)
        elif p.action == "add_project":
            skeleton.capabilities.projects_built.append(p.proposed_value)

    skeleton.connection_surface = sync_tags(skeleton)

    # Write to YAML with comments
    write_dossier_with_comments(dossier_path, skeleton)
    # ... print summary
```

### 5.3 `pd dossier show`

**Purpose:** Display the dossier in a formatted, human-readable Rich terminal output. Useful for quick review without opening the YAML file.

**Options:**
```
pd dossier show [OPTIONS]

Options:
  --layer <N>     Show only a specific layer (1-5). Default: show all.
  --tags-only     Show only Layer 5 (connection_surface) tags. Compact view.
```

**Example output (`pd dossier show --tags-only`):**

```
$ pd dossier show --tags-only

🛡️ Operator Connection Surface (Layer 5)

  Experience:   military, career-pivot, self-taught, research, open-source
  Topics:       verification, forensic-auditing, ML-pipeline, developer-tooling,
                async-python, diffusion-models, compositional-gap, agent-safety
  Geography:    charleston-sc, san-francisco-ca
  Education:    university-of-example, computer-science, artificial-intelligence
  Industries:   defense, AI-agents, devtools, environmental, fintech
  Hobbies:      backpacking, chess, technical-writing, open-source
  Philosophy:   verification-over-trust, ownership, systems-thinking,
                craft-over-speed, anti-hype

  Total tags: 31 across 7 categories
```

**Example output (`pd dossier show --layer 2`):**

```
$ pd dossier show --layer 2

🛡️ Operator Dossier — Layer 2: Technical Capabilities

──── Skills (6) ─────────────────────────────────────

  Python           ███████████ expert    (active)
  asyncio          ████████░░░ proficient (active)
  PyTorch          ████████░░░ proficient (active)
  TypeScript       ████████░░░ proficient (active)
  SQLite/SQLModel  ████████░░░ proficient (active)
  Docker           ████░░░░░░░ familiar  (recent)

──── Domain Expertise (8) ───────────────────────────

  forensic-auditing, verification-systems, ML-pipeline,
  environmental-data, nuclear-electronics, developer-tooling,
  AST-mutation-testing, agent-safety

──── Projects Built (3) ─────────────────────────────

  prime-directive   Python, Typer, SQLModel, Hydra, Rich, asyncio
  rna-predict       Python, PyTorch, Hydra, pytest
  black-box         TypeScript, Next.js, Prisma, PostgreSQL

──── Methodologies (2) ──────────────────────────────

  AIV Protocol      AI-Integrated Verification
  SVP Protocol      Sovereign Verification Protocol
```

### 5.4 `pd dossier validate`

**Purpose:** Parse the dossier YAML, check all validation rules (§3), and report errors and warnings.

**Validation checks:**

| Check | Severity | Description |
|-------|----------|-------------|
| YAML parse | ERROR | File must be valid YAML. |
| Version match | ERROR | `version` must be `"3.1"`. |
| Skill depth enum | ERROR | `skills[*].depth` must be `expert`, `proficient`, or `familiar`. |
| Skill recency enum | ERROR | `skills[*].recency` must be `active`, `recent`, or `historical`. |
| Tag normalization | WARNING | All tags should be lowercase, hyphenated. Auto-fix offered. |
| Tag duplicates | WARNING | No duplicates within a tag category. |
| Tag count limit | WARNING | No more than 50 tags per category. |
| Tech stack cross-ref | WARNING | `projects_built[*].tech_stack` entries should have corresponding `skills` entries. |
| Empty layers | INFO | Reports which layers have no content (guides the operator on what to fill). |
| Philosophy tags present | INFO | Flags if `connection_surface.philosophy_tags` is empty (reminder to populate). |

**Example output:**

```
$ pd dossier validate

🛡️ Dossier Validation Report

  ✅ YAML syntax: valid
  ✅ Version: 3.1
  ✅ Skills: 6 entries, all valid enums
  ⚠️  Tag normalization: "Long-distance backpacking" → "long-distance-backpacking" (auto-fix? Y/n)
  ⚠️  Tech stack cross-ref: "Prisma" in black-box tech_stack but no matching skill entry
  ℹ️  Empty layers: identity.military, identity.publications
  ℹ️  connection_surface.philosophy_tags: 5 tags present

  Result: 0 errors, 2 warnings, 2 info
```

### 5.5 `pd dossier sync-skills`

**Purpose:** Scan all repos in `config.yaml` for dependency files, compare against existing dossier skills, and propose additions.

**Options:**
```
pd dossier sync-skills [OPTIONS]

Options:
  --apply         Automatically apply all proposals (skip interactive review).
  --dry-run       Show proposals without modifying the dossier. Default behavior.
  --deep          Also scan ContextSnapshot history for recurring themes (uses cheap LLM).
```

**Example output (default/dry-run):**

```
$ pd dossier sync-skills

🛡️ Skill Sync — Scanning 4 repositories...

  Scanning prime-directive/pyproject.toml...  12 deps found
  Scanning rna-predict/pyproject.toml...      8 deps found
  Scanning black-box/package.json...          24 deps found
  Scanning bluethumb/pyproject.toml...        5 deps found

──── Proposed Additions ─────────────────────────────

  NEW SKILL: "httpx" (familiar, active)
    Source: prime-directive/pyproject.toml
    Confidence: 0.8

  NEW SKILL: "Next.js" (familiar, active)
    Source: black-box/package.json
    Confidence: 0.8

  NEW SKILL: "Prisma" (familiar, active)
    Source: black-box/package.json
    Confidence: 0.8

  UPDATED PROJECT: bluethumb
    Added to projects_built from empire.yaml
    Tech stack: [Python, Flask, SQLAlchemy]

──── Summary ────────────────────────────────────────

  3 new skills proposed
  1 new project proposed
  0 existing skills updated

  Run 'pd dossier sync-skills --apply' to accept all,
  or edit ~/.prime-directive/operator_dossier.yaml manually.
```

**The `--deep` flag:** When passed, the command also queries the last 30 days of `ContextSnapshot` entries (specifically `human_objective`, `human_blocker`, and `human_note` fields) and uses the cheap LLM to extract recurring topic themes. These are proposed as `domain_expertise` tag candidates. This is the only LLM-dependent feature in V3.1.

```
$ pd dossier sync-skills --deep

[... standard scan output ...]

──── Deep Analysis (LLM) ────────────────────────────

  Scanned 47 snapshots across 4 repos (last 30 days)

  SUGGESTED domain_expertise tag: "gradient-debugging"
    Evidence: 8 snapshots mention gradient explosion/vanishing
    Confidence: 0.7

  SUGGESTED domain_expertise tag: "async-migration"
    Evidence: 5 snapshots describe sync-to-async refactoring
    Confidence: 0.6

  Cost: 1,200 tokens ($0.0006)
```

### 5.6 `pd dossier sync-tags`

**Purpose:** Regenerate Layer 5 (`connection_surface`) from Layers 1–4 using the deterministic derivation algorithm (§4.5).

**Behavior:**
- Runs the `sync_tags()` function.
- Shows a diff between the current Layer 5 and the newly derived Layer 5.
- Preserves `philosophy_tags` (manual).
- Writes the updated Layer 5 to the dossier file.

```
$ pd dossier sync-tags

🛡️ Tag Sync — Deriving connection_surface from Layers 1-4

  experience_tags:  5 tags (unchanged)
  topic_tags:       8 → 9 tags (+1: "gradient-debugging")
  geographic_tags:  2 tags (unchanged)
  education_tags:   3 tags (unchanged)
  industry_tags:    5 tags (unchanged)
  hobby_tags:       4 tags (unchanged)
  philosophy_tags:  5 tags (preserved, manual)

  Total: 31 → 32 tags

  Updated ~/.prime-directive/operator_dossier.yaml
```

### 5.7 `pd dossier export`

**Purpose:** Export the dossier in a format consumable by external systems. The primary consumer is the `black-box` outreach platform.

**Options:**
```
pd dossier export [OPTIONS]

Options:
  --format <fmt>   Output format: "json" (default), "yaml", "tags-only"
  --output <path>  Write to file instead of stdout. Default: stdout.
  --layer5-only    Export only the connection_surface (Layer 5).
```

**Example (`pd dossier export --format json --layer5-only`):**

```json
{
  "version": "3.1",
  "connection_surface": {
    "experience_tags": ["military", "career-pivot", "self-taught", "research", "open-source"],
    "topic_tags": ["verification", "forensic-auditing", "ML-pipeline", "developer-tooling", "async-python", "diffusion-models", "compositional-gap", "agent-safety", "code-quality"],
    "geographic_tags": ["charleston-sc", "san-francisco-ca"],
    "education_tags": ["university-of-example", "computer-science", "artificial-intelligence"],
    "industry_tags": ["defense", "AI-agents", "devtools", "environmental", "fintech"],
    "hobby_tags": ["backpacking", "chess", "technical-writing", "open-source"],
    "philosophy_tags": ["verification-over-trust", "ownership", "systems-thinking", "craft-over-speed", "anti-hype"]
  }
}
```

This JSON output is the **integration contract** that `black-box` consumes. The next section (§6) specifies exactly how `black-box` uses this data.

---

## 6. black-box Integration Contract

This section defines the formal interface between Prime Directive (the producer of operator identity data) and the `black-box` outreach platform (the consumer). The contract ensures both systems can evolve independently while maintaining compatibility.

### 6.1 Responsibility Boundary

The division of labor is strict and unambiguous:

| Responsibility | Owner | NOT the other's job |
|---------------|-------|---------------------|
| Maintain `operator_dossier.yaml` | **Prime Directive** | black-box never writes to the dossier. |
| Export operator identity as JSON | **Prime Directive** | black-box never parses the YAML directly. |
| Store and profile outreach targets | **black-box** | PD never stores target data. |
| Compute `operator ∩ target` intersection | **black-box** | PD does not know about targets. |
| Generate outreach messages (SMYKM) | **black-box** | PD does not compose outreach. |
| Rank targets by intersection score | **black-box** | PD does not rank people. |

**The dossier JSON export is the API.** Prime Directive produces it; black-box consumes it. There is no shared database, no shared code, no RPC, no message queue. The integration is a file read.

### 6.2 The Integration Data Flow

```
Prime Directive                              black-box
──────────────                               ─────────

operator_dossier.yaml
       │
       │ pd dossier export --format json
       ▼
operator_dossier.json  ──── file read ────→  loadOperatorDossier()
                                                    │
                                                    ├── target.extractedSignals
                                                    │         │
                                                    ▼         ▼
                                              computeIntersection(operator, target)
                                                    │
                                                    ▼
                                              IntersectionResult {
                                                score: number,
                                                matches: Match[],
                                                suggested_hooks: string[]
                                              }
                                                    │
                                                    ▼
                                              SMYKM prompt construction
                                                    │
                                                    ▼
                                              Outreach message draft
```

### 6.3 Export Schema (What black-box Receives)

The full export JSON schema is defined by the `OperatorDossier` dataclass (§3.7). For intersection scoring, black-box primarily consumes Layer 5 (`connection_surface`), but may read Layers 1–4 for outreach message enrichment.

**Minimum viable export (Layer 5 only):**

```typescript
// black-box type definition for the operator dossier
interface OperatorConnectionSurface {
  version: string;                    // "3.1"
  connection_surface: {
    experience_tags: string[];        // e.g., ["military", "career-pivot"]
    topic_tags: string[];             // e.g., ["verification", "ML-pipeline"]
    geographic_tags: string[];        // e.g., ["charleston-sc"]
    education_tags: string[];         // e.g., ["university-of-example"]
    industry_tags: string[];          // e.g., ["defense", "AI-agents"]
    hobby_tags: string[];             // e.g., ["backpacking", "chess"]
    philosophy_tags: string[];        // e.g., ["craft-over-speed"]
  };
}
```

**Full export (all layers, for outreach enrichment):**

```typescript
interface OperatorDossier {
  version: string;
  identity: {
    education: Array<{ institution: string; degree: string; field: string; years: string }>;
    military?: { branch: string; rate_mos: string; specialty: string; stations: string[] };
    geographic_history: Array<{ location: string; years: string }>;
    hobbies: string[];
    formative_experiences: string[];
    intellectual_influences: string[];
    values: string[];
    publications: Array<{ title: string; venue: string; year: number; tags: string[] }>;
  };
  capabilities: {
    skills: Array<{ name: string; depth: string; recency: string; evidence: string }>;
    domain_expertise: string[];
    projects_built: Array<{
      name: string; description: string;
      tech_stack: string[]; capability_tags: string[];
    }>;
    methodologies: Array<{ name: string; description: string; applicable_contexts: string[] }>;
  };
  network: {
    companies: Array<{ name: string; role: string; years: string }>;
    industries: string[];
    institutional_overlaps: Array<{ type: string; value: string }>;
  };
  positioning: {
    positioning_statement: string;
    competitive_differentiation: string[];
    offerings: Array<{ name: string; description: string }>;
    case_studies: Array<{ title: string; outcome: string }>;
  };
  connection_surface: OperatorConnectionSurface["connection_surface"];
}
```

### 6.4 The Intersection Scoring Algorithm

This algorithm runs in black-box, not in Prime Directive. It is specified here because the dossier schema was designed to enable it. The algorithm computes a weighted overlap between the operator's `connection_surface` tags and the target's `extractedSignals` tags.

**Prerequisite:** black-box must normalize its `ExtractedSignals` into the same tag format as the dossier (lowercase, hyphenated). This normalization is black-box's responsibility.

```typescript
interface IntersectionResult {
  total_score: number;           // 0.0 - 1.0
  category_scores: Record<string, CategoryScore>;
  top_matches: Match[];          // Sorted by weight, descending
  suggested_hooks: string[];     // Human-readable connection points
}

interface CategoryScore {
  category: string;
  operator_tags: string[];
  target_tags: string[];
  overlap: string[];
  score: number;                 // |overlap| / max(|operator|, |target|)
  weight: number;                // Category weight
  weighted_score: number;        // score * weight
}

interface Match {
  category: string;
  tag: string;
  weight: number;
}

const CATEGORY_WEIGHTS: Record<string, number> = {
  philosophy_tags: 3.0,      // Shared values are the strongest connection
  experience_tags: 2.5,      // Shared life experiences (military, career pivots)
  topic_tags: 2.0,           // Shared technical interests
  hobby_tags: 1.5,           // Shared personal interests
  industry_tags: 1.5,        // Shared professional context
  geographic_tags: 1.0,      // Shared places
  education_tags: 1.0,       // Shared institutions
};

function computeIntersection(
  operator: OperatorConnectionSurface,
  target: NormalizedTargetSignals
): IntersectionResult {
  const categories = Object.keys(CATEGORY_WEIGHTS);
  const categoryScores: Record<string, CategoryScore> = {};
  const allMatches: Match[] = [];

  let totalWeightedScore = 0;
  let totalWeight = 0;

  for (const category of categories) {
    const opTags = new Set(operator.connection_surface[category] || []);
    const tgTags = new Set(target[category] || []);
    const overlap = [...opTags].filter(t => tgTags.has(t));
    const maxSize = Math.max(opTags.size, tgTags.size);
    const score = maxSize > 0 ? overlap.length / maxSize : 0;
    const weight = CATEGORY_WEIGHTS[category];

    categoryScores[category] = {
      category,
      operator_tags: [...opTags],
      target_tags: [...tgTags],
      overlap,
      score,
      weight,
      weighted_score: score * weight,
    };

    totalWeightedScore += score * weight;
    totalWeight += weight;

    for (const tag of overlap) {
      allMatches.push({ category, tag, weight });
    }
  }

  // Sort matches by category weight (most meaningful first)
  allMatches.sort((a, b) => b.weight - a.weight);

  return {
    total_score: totalWeight > 0 ? totalWeightedScore / totalWeight : 0,
    category_scores: categoryScores,
    top_matches: allMatches.slice(0, 10),
    suggested_hooks: generateHooks(allMatches, operator, target),
  };
}
```

**Category weight rationale:**
- **Philosophy (3.0):** Shared values create the deepest, most authentic connections. "We both believe in verification over trust" is a stronger bond than "we both use Python."
- **Experience (2.5):** Shared life experiences (military service, career pivots) create instant rapport that transcends professional context.
- **Topics (2.0):** Shared technical interests are the most actionable for professional connection — they give you something concrete to discuss.
- **Hobbies & Industries (1.5):** Good conversation starters but less deep than shared values or experiences.
- **Geography & Education (1.0):** "I lived there too" or "I went there too" are useful but surface-level hooks.

### 6.5 Hook Generation

The `generateHooks()` function translates raw tag overlaps into human-readable connection sentences that can seed an outreach message:

```typescript
function generateHooks(
  matches: Match[],
  operator: OperatorDossier,
  target: NormalizedTargetSignals
): string[] {
  const hooks: string[] = [];

  for (const match of matches.slice(0, 5)) {
    switch (match.category) {
      case "philosophy_tags":
        hooks.push(
          `Shared value: "${match.tag}". ` +
          `You both prioritize ${match.tag.replace(/-/g, " ")}.`
        );
        break;
      case "experience_tags":
        if (match.tag === "military") {
          hooks.push(
            `Both have military backgrounds. ` +
            `Operator: ${operator.identity.military?.branch || "military service"}.`
          );
        } else {
          hooks.push(`Shared experience: ${match.tag.replace(/-/g, " ")}.`);
        }
        break;
      case "topic_tags":
        hooks.push(
          `Shared technical interest: ${match.tag.replace(/-/g, " ")}. ` +
          `Potential for deep technical discussion.`
        );
        break;
      case "geographic_tags":
        hooks.push(
          `Geographic overlap: both have ties to ${match.tag.replace(/-/g, " ")}.`
        );
        break;
      case "hobby_tags":
        hooks.push(
          `Shared hobby: ${match.tag.replace(/-/g, " ")}. ` +
          `Opens a personal, non-professional conversation thread.`
        );
        break;
      default:
        hooks.push(
          `Overlap in ${match.category}: ${match.tag.replace(/-/g, " ")}.`
        );
    }
  }
  return hooks;
}
```

### 6.6 Worked Example: Intersection with a Target

**Operator tags** (from dossier export):
```
experience:  military, career-pivot, self-taught, research, open-source
topics:      verification, forensic-auditing, ML-pipeline, developer-tooling
hobbies:     backpacking, chess, technical-writing
philosophy:  verification-over-trust, ownership, craft-over-speed
geography:   charleston-sc, san-francisco-ca
industries:  defense, AI-agents, devtools
```

**Target "Patrick" tags** (from black-box ExtractedSignals, normalized):
```
experience:  startup-founder, open-source
topics:      code-quality, developer-tooling, CI-CD, verification
hobbies:     backpacking, surfing, scuba
philosophy:  ownership, craft-over-speed, systems-thinking
geography:   san-francisco-ca, minneapolis-mn
industries:  devtools, fintech
```

**Intersection result:**

| Category | Overlap | Score | × Weight | Weighted |
|----------|---------|-------|----------|----------|
| philosophy | ownership, craft-over-speed | 2/3 = 0.67 | × 3.0 | 2.00 |
| experience | open-source | 1/5 = 0.20 | × 2.5 | 0.50 |
| topics | verification, developer-tooling | 2/5 = 0.40 | × 2.0 | 0.80 |
| hobbies | backpacking | 1/3 = 0.33 | × 1.5 | 0.50 |
| industries | devtools | 1/3 = 0.33 | × 1.5 | 0.50 |
| geography | san-francisco-ca | 1/2 = 0.50 | × 1.0 | 0.50 |
| education | (none) | 0 | × 1.0 | 0.00 |
| **Total** | | | **/ 12.0** | **4.80 / 12.0 = 0.40** |

**Generated hooks:**
1. "Shared value: ownership. You both prioritize ownership."
2. "Shared value: craft-over-speed. You both prioritize craft over speed."
3. "Shared technical interest: verification. Potential for deep technical discussion."
4. "Shared technical interest: developer-tooling. Potential for deep technical discussion."
5. "Shared hobby: backpacking. Opens a personal, non-professional conversation thread."

**Score interpretation:**
- 0.40 is a **MODERATE match** — enough shared surface for a genuine, multi-hook outreach message.
- The strongest signal is philosophy alignment (shared `ownership` and `craft-over-speed` values).
- The `backpacking` hobby overlap provides a warm, personal opening that differentiates from generic professional outreach.

### 6.7 Version Compatibility

The integration contract includes a `version` field in the JSON export. black-box should check this field and handle version mismatches:

| Dossier Version | black-box Behavior |
|-----------------|-------------------|
| `"3.1"` | Full support. All tag categories available. |
| Unknown/missing | Fall back to Layer 5 only. Warn if categories are missing. |
| Future `"3.2"+` | Forward-compatible. Unknown categories are ignored. Known categories are consumed normally. |

This ensures that upgrading the dossier schema in Prime Directive does not break the black-box integration, and vice versa.

---

## 7. Data Flow & The Strategic Flywheel

This section maps the complete data flow from daily development activity through identity maintenance to outreach execution, and describes the feedback loop that makes the system self-reinforcing.

### 7.1 The Three Systems

The full vision spans three systems, each with a distinct role:

| System | Role | Metaphor |
|--------|------|----------|
| **Prime Directive V1.x** | Tactical context preservation | "Save game" |
| **Prime Directive V3.0** | Portfolio prioritization | "Game guide" |
| **Prime Directive V3.1** | Operator identity management | "Character sheet" |
| **black-box** | Outreach intelligence & execution | "Diplomacy engine" |

V3.1 is the bridge. It takes raw data from V1.x/V3.0 (snapshots, heartbeats, empire metadata) and structures it into an identity model that black-box can consume for outreach.

### 7.2 End-to-End Data Flow

```
DAILY WORK (continuous)
═══════════════════════

Developer writes code, commits, switches projects
        │
        ▼
pd freeze  ──→  ContextSnapshot (DB)
        │              │
        │              ├── git_status_summary
        │              ├── human_objective      ──┐
        │              ├── human_blocker         ──┤
        │              └── human_note            ──┤
        │                                         │
        ▼                                         │
RepositoryHeartbeat (DB)                          │
        │                                         │
        └── status, summary, confidence           │
                                                  │
                                                  │
PORTFOLIO MANAGEMENT (on demand)                  │
════════════════════════════════                   │
                                                  │
pd overseer  ──→  Ranked project list             │
        │              │                          │
        │              ├── scores + directives     │
        │              └── strategic alignment     │
        │                                         │
        │                                         │
IDENTITY MAINTENANCE (periodic)                   │
═══════════════════════════════                   │
                                                  │
pd dossier sync-skills  ◄────────────────────────┘
        │                     reads snapshots (--deep)
        │                     reads pyproject.toml, package.json
        │                     reads empire.yaml
        ▼
operator_dossier.yaml
        │
        ├── Layer 2: skills, projects (SEMI-AUTOMATED)
        │
        │   (operator fills Layers 1, 3, 4 manually)
        │
        ▼
pd dossier sync-tags
        │
        ├── Layer 5: connection_surface (DERIVED)
        ▼
pd dossier export --format json
        │
        │
OUTREACH EXECUTION (in black-box)
══════════════════════════════════
        │
        ▼
black-box: loadOperatorDossier()
        │
        ├── target.extractedSignals
        │
        ▼
computeIntersection(operator, target)
        │
        ├── IntersectionResult
        │   ├── score: 0.40
        │   ├── top_matches: [philosophy, topics, hobbies]
        │   └── suggested_hooks: [5 connection sentences]
        │
        ▼
SMYKM prompt + outreach draft
        │
        ▼
Sent to target
        │
        │
FEEDBACK LOOP (future V3.2)
════════════════════════════
        │
        ▼
New partnership / project / engagement
        │
        ├── New repo added to config.yaml
        ├── empire.yaml updated
        ├── strategy.md updated with new goals
        │
        ▼
pd overseer re-ranks portfolio
        │
        ▼
pd dossier sync-skills detects new project
        │
        ▼
Dossier updated → new capability tags → better outreach matching
```

### 7.3 The Flywheel Effect

The strategic flywheel is the second-order payoff of integrating these systems. It creates a self-reinforcing cycle:

```
Work on projects
      │
      ▼
Build skills & capabilities ───→ Dossier grows
      │                                │
      │                                ▼
      │                    Better intersection scores
      │                                │
      │                                ▼
      │                    More effective outreach
      │                                │
      │                                ▼
      │                    New partnerships & opportunities
      │                                │
      │                                ▼
      └──────── New projects ◄─────────┘
```

**Each cycle strengthens the next:**

1. **Working on projects** generates snapshots and heartbeats, which feed the dossier's skill inventory.
2. **A richer dossier** produces higher intersection scores with more targets, because you have more tags to match against.
3. **Higher intersection scores** enable more genuine, multi-hook outreach messages that get higher response rates.
4. **Successful outreach** leads to new projects, partnerships, or engagements.
5. **New projects** get added to `empire.yaml` and `config.yaml`, generating new snapshots and heartbeats.
6. **The dossier grows again** with new skills, domains, and capability tags.

### 7.4 Concrete Second-Order Effects

Beyond the flywheel, the structured dossier enables specific strategic analyses:

#### 7.4.1 Capability Gap Analysis

**Question:** "What skills do my top 10 outreach targets care about that I don't have?"

**Process:**
1. Export the dossier's `topic_tags`.
2. Aggregate the `topic_tags` of the top 10 targets from black-box.
3. Compute `target_union - operator_tags` = **capability gaps**.

**Example output:**
```
Capability gaps vs. top 10 targets:
  "kubernetes"          — appears in 7/10 targets, absent from dossier
  "observability"       — appears in 5/10 targets, absent from dossier
  "distributed-systems" — appears in 4/10 targets, absent from dossier

Recommendation: Consider a project involving Kubernetes or observability
to fill the highest-value gap.
```

This directly feeds V3.0 portfolio prioritization — the operator can adjust `strategy.md` to focus on projects that build missing capabilities.

#### 7.4.2 Outreach Sequencing

**Question:** "Which targets should I reach out to first?"

**Process:**
1. Run `computeIntersection()` for all targets.
2. Sort by `total_score` descending.
3. Contact highest-overlap targets first (highest probability of genuine connection).

#### 7.4.3 Narrative Coherence Audit

**Question:** "Am I presenting a consistent story across all channels?"

**Process:**
1. Compare `positioning.positioning_statement` against `capabilities.domain_expertise`.
2. Flag mismatches: if your positioning says "forensic technical due diligence" but your domain tags don't include `forensic-auditing`, the narrative is incoherent.
3. Compare `values` against `philosophy_tags` — ensure the keyword distillation is accurate.

#### 7.4.4 Project Portfolio ROI (Identity-Weighted)

**Question:** "Which of my projects contributes the most to my dossier's outreach effectiveness?"

**Process:**
1. For each project in `empire.yaml`, count how many of its `capability_tags` appear in the aggregate target tag pool.
2. The project with the most overlap is the highest-ROI project for outreach purposes.
3. Compare this ranking against V3.0's `pd overseer` ranking — if they differ, the operator has a strategic decision to make: optimize for execution (V3.0's recommendation) or optimize for leverage (V3.1's analysis).

### 7.5 What V3.1 Implements vs. Future Work

| Analysis | V3.1 Status | Notes |
|----------|------------|-------|
| Dossier maintenance (sync-skills, sync-tags) | ✅ Implemented | Core deliverable. |
| Dossier export for black-box consumption | ✅ Implemented | Core deliverable. |
| Intersection scoring algorithm | 📋 Specified (§6.4) | Implemented in black-box, not PD. |
| Capability gap analysis | 📋 Specified (§7.4.1) | Implemented in black-box. Requires aggregating target tags. |
| Outreach sequencing | 📋 Specified (§7.4.2) | Implemented in black-box. |
| Narrative coherence audit | ❌ Future | Could be a `pd dossier audit` command in V3.2. |
| Identity-weighted project ROI | ❌ Future | Requires V3.2 feedback loop between dossier and overseer. |
| V3.0 scoring factor from dossier gaps | ❌ Future (V3.2) | Would add an 8th scoring factor to `pd overseer`: "identity leverage." |

---

## 8. Implementation Roadmap

### 8.1 Prerequisites

V3.1 has a **hard dependency** on V3.0 Phase 1 (Data Foundation). Specifically:

| V3.0 Component | Required By V3.1 | Reason |
|----------------|-------------------|--------|
| `empire.yaml` parser (`core/empire.py`) | `pd dossier sync-skills` | Reads project metadata (domain, role, description) to seed Layer 2. |
| `config.yaml` repo paths | `pd dossier sync-skills` | Locates repo directories to scan dependency files. |
| `RepositoryHeartbeat` table | Optional (`sync-skills --deep`) | Can extract themes from snapshot history. Not required for core functionality. |
| AI provider infrastructure | Optional (`sync-skills --deep`) | Reused for cheap LLM calls during deep theme extraction. |

**V3.1 does NOT depend on:**
- V3.0 Phase 2 (Scoring Engine) — the dossier doesn't consume scoring data.
- V3.0 Phase 3 (LLM Validation) — the dossier doesn't consume validation data.
- V3.0 Phase 4 (Polish) — no dependency on onboarding wizard or doctor extension.

This means V3.1 implementation can begin **as soon as V3.0 Phase 1 is complete**, running in parallel with V3.0 Phases 2–4.

### 8.2 Implementation Phases

#### Phase A: Schema & Parser (1 session)

**Goal:** Define the `operator_dossier.yaml` schema and implement the parser with full validation.

**Deliverables:**
1. `core/identity.py` — Parser for `operator_dossier.yaml`. All 5 layer dataclasses. YAML loading, validation, and error reporting.
2. `pd dossier validate` command in `bin/pd.py`.
3. `pd dossier init` command — generates skeleton YAML.
4. Tests: `test_identity.py` — valid parse, missing fields, invalid enums, version mismatch, empty layers.

**Estimated tests:** 15  
**Dependencies:** None (can start immediately, even before V3.0).

#### Phase B: Skill Scanner (1 session)

**Goal:** Implement automated dependency scanning across all repos.

**Deliverables:**
1. `core/skill_scanner.py` — Scanners for `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`. Proposal generation with confidence scores.
2. `pd dossier sync-skills` command (dry-run and --apply modes).
3. Integration with `empire.yaml` for project auto-detection.
4. Tests: `test_skill_scanner.py` — each scanner in isolation, proposal deduplication, confidence scoring, no-deletion invariant.

**Estimated tests:** 12  
**Dependencies:** V3.0 Phase 1 (`empire.yaml` parser must exist for project auto-detection).

#### Phase C: Tag Derivation & Export (1 session)

**Goal:** Implement Layer 5 derivation and the export pipeline.

**Deliverables:**
1. `sync_tags()` function in `core/identity.py` — deterministic derivation of Layer 5 from Layers 1–4.
2. `pd dossier sync-tags` command.
3. `pd dossier export` command — JSON, YAML, and tags-only formats.
4. `pd dossier show` command — Rich-formatted terminal output for all layers.
5. Tests: `test_identity.py` (extended) — tag derivation correctness, normalization, deduplication, philosophy_tags preservation, JSON export schema compliance.

**Estimated tests:** 10  
**Dependencies:** Phase A (parser must exist).

#### Phase D: Deep Analysis & Polish (1 session, optional)

**Goal:** Add LLM-powered theme extraction from snapshot history and final CLI polish.

**Deliverables:**
1. `--deep` flag for `sync-skills` — queries `ContextSnapshot` table, sends to cheap LLM for theme extraction.
2. Budget enforcement for deep analysis (reuses V3.0 AI provider infrastructure).
3. Shell completion update — add `dossier` subcommands to completion list.
4. Documentation — update `docs/index.md`, README.md with dossier commands.
5. Tests: `test_skill_scanner.py` (extended) — deep analysis with mocked LLM, budget enforcement.

**Estimated tests:** 5  
**Dependencies:** Phase B + V3.0 Phase 1 (AI provider infrastructure and ContextSnapshot table).

### 8.3 Task Dependency Graph

```
V3.0 Phase 1          V3.1 Phase A        V3.1 Phase B        V3.1 Phase C
(Data Foundation)      (Schema & Parser)   (Skill Scanner)     (Tags & Export)
────────────────       ─────────────────   ─────────────────   ───────────────

empire.yaml parser ──→ (not required) ──→ sync-skills ──────→ sync-tags
config.yaml ─────────→ (not required) ──→ repo scanning       export
                                                               show
identity.py ◄──── Phase A ──────────────────────────────────→ Phase C
                       │
                       ├── validate
                       └── init

                                            V3.1 Phase D
                                            (Deep + Polish)
                                            ───────────────
                                            --deep flag
                                            shell completion
                                            docs update
```

### 8.4 Testing Strategy

**Total estimated new tests: ~42**

| Module | Test File | Key Test Cases | Est. Tests |
|--------|-----------|---------------|------------|
| `core/identity.py` | `tests/test_identity.py` | Valid parse, missing fields, invalid enums, version mismatch, empty layers, tag derivation, normalization, deduplication, philosophy preservation, JSON export | 25 |
| `core/skill_scanner.py` | `tests/test_skill_scanner.py` | pyproject.toml scanning, package.json scanning, Cargo.toml scanning, go.mod scanning, proposal dedup, confidence scoring, no-deletion, empire project detection, deep LLM analysis | 12 |
| CLI commands | `tests/test_dossier_cli.py` | init (new file, existing file), validate (valid, errors, warnings), sync-skills dry-run, export JSON format | 5 |

**Test infrastructure:**
- All tests use `tmp_path` for isolated dossier files.
- Skill scanner tests include fixture repos with known dependency files.
- No live LLM calls — deep analysis tests use mocked responses.
- Existing V1.x and V3.0 test suites are unchanged.

### 8.5 Cost Analysis

V3.1 adds minimal cost to the system:

| Operation | Model | Cost/Call | Frequency | Monthly Cost |
|-----------|-------|-----------|-----------|-------------|
| `sync-skills` (standard) | None (file scanning) | $0.00 | ~4/month | $0.00 |
| `sync-skills --deep` | `qwen2.5-coder` (Ollama) | $0.00 (local) | ~2/month | $0.00 |
| `sync-skills --deep` (fallback) | `gpt-4o-mini` | ~$0.001 | ~1/month | ~$0.001 |
| `sync-tags` | None (deterministic) | $0.00 | ~4/month | $0.00 |
| `export` | None (serialization) | $0.00 | ~4/month | $0.00 |

**V3.1 adds effectively zero cost to the monthly AI budget.** The only LLM usage is the optional `--deep` flag, which uses the cheap model and runs infrequently.

### 8.6 Migration: Adding V3.1 to an Existing V3.0 Installation

Like V3.0, V3.1 requires **zero migration steps**:

1. **Update the package.** The new commands are available immediately.
2. **No database changes.** V3.1 does not add or modify any database tables.
3. **No config changes.** V3.1 reads existing `config.yaml` and `empire.yaml` but does not extend them.
4. **The dossier file is new.** It is created by `pd dossier init` when the operator is ready.
5. **All existing commands unchanged.** V1.x commands, V3.0 `pd overseer` — all work identically.

### 8.7 Rollback Plan

1. **Delete the dossier file.** `rm ~/.prime-directive/operator_dossier.yaml`. No side effects on any other system.
2. **Ignore the commands.** `pd dossier *` commands have zero side effects when not used. They don't modify the database, don't modify config files, and don't affect V1.x or V3.0 behavior.
3. **black-box integration is optional.** If the dossier export doesn't exist, black-box falls back to its existing (non-dossier) outreach workflow.

---

## 9. Summary

V3.1 — The Operator Identity Protocol — fills the gap identified by the critique of V3.0: the absence of a structured, machine-readable representation of the operator's identity.

**What it delivers:**
- A 5-layer YAML schema (`operator_dossier.yaml`) capturing who the operator is, what they can build, who knows them, what they offer, and a machine-readable tag index.
- A `pd dossier` command suite for maintaining, validating, and exporting the dossier.
- A formal integration contract with black-box for automated `operator ∩ target` intersection scoring.
- An honest automation analysis: ~25% automated initially, ~60% for ongoing maintenance.

**What it does NOT deliver:**
- Outreach execution (black-box's domain).
- Target profiling (black-box's domain).
- Automated philosophy inference (unreliable, intentionally manual).
- Feedback loop into V3.0 scoring (future V3.2).

**The architectural relationship:**

```
V1.x (Save Game) → V3.0 (Game Guide) → V3.1 (Character Sheet) → black-box (Diplomacy)
     tactical            strategic             identity                outreach
```

Each layer builds on the previous. Each is independently valuable. Together, they form a unified system for managing execution, optimizing leverage, and building genuine connections.

---

*End of Document*

**Document:** PD-ARCH-V3.1-IDENTITY — The Operator Identity Protocol  
**Sections:** 9 sections, ~1800 lines  
**Status:** Ready for implementation after V3.0 Phase 1 completes  
**Prerequisite:** PD-ARCH-V3.0-GRAND-STRATEGIST.md

