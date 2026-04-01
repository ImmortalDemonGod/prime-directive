from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
import json
from pathlib import Path
import re
import tomllib
from typing import Any

from prime_directive.core.empire import ProjectRole, load_empire_if_exists
from prime_directive.core.identity import (
    OperatorDossier,
    ProjectBuilt,
    Skill,
    normalize_tag,
)

RUNTIME_CONFIDENCE = 0.8
DEV_CONFIDENCE = 0.5
LANGUAGE_CONFIDENCE = 0.95
ROLE_CAPABILITY_TAGS = {
    ProjectRole.RESEARCH: ["research"],
    ProjectRole.INFRASTRUCTURE: ["infrastructure"],
    ProjectRole.MAINTENANCE: ["maintenance"],
    ProjectRole.EXPERIMENTAL: ["experimental"],
}

SKILL_ALIASES = {
    "@prisma/client": "Prisma",
    "next": "Next.js",
    "prisma": "Prisma",
    "pyyaml": "PyYAML",
    "react": "React",
    "react-dom": "React",
    "sqlmodel": "SQLModel",
    "typescript": "TypeScript",
}

_REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "been",
    "before",
    "between",
    "build",
    "built",
    "change",
    "changes",
    "debug",
    "doing",
    "from",
    "have",
    "into",
    "more",
    "need",
    "next",
    "note",
    "notes",
    "repo",
    "session",
    "should",
    "step",
    "that",
    "them",
    "then",
    "this",
    "update",
    "using",
    "with",
    "work",
}


@dataclass(frozen=True)
class DetectedSkill:
    skill_name: str
    source: str
    confidence: float


@dataclass(frozen=True)
class RepoScanSummary:
    repo_id: str
    source_files: list[str] = field(default_factory=list)
    detected_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncProposal:
    action: str
    repo_id: str
    value_name: str
    source: str
    confidence: float
    project_tech_stack: list[str] = field(default_factory=list)
    project_description: str = ""
    project_capability_tags: list[str] = field(default_factory=list)
    project_url: str | None = None


@dataclass(frozen=True)
class ThemeSuggestion:
    tag: str
    occurrences: int
    sample: str
    confidence: float = 0.0


def build_sync_proposals(
    cfg: Any,
    dossier: OperatorDossier,
) -> tuple[list[RepoScanSummary], list[SyncProposal]]:
    existing_skills = {
        skill.name.strip().lower()
        for skill in dossier.capabilities.skills
        if skill.name.strip()
    }
    existing_projects = {
        project.name.strip().lower()
        for project in dossier.capabilities.projects_built
        if project.name.strip()
    }

    summaries: list[RepoScanSummary] = []
    proposals: list[SyncProposal] = []
    empire = load_empire_if_exists(cfg)
    empire_projects = empire.projects if empire is not None else {}

    for repo_id, repo_cfg in cfg.repos.items():
        repo_path = Path(str(repo_cfg.path)).expanduser()
        detected = scan_repository(repo_path)
        tech_stack = sorted({item.skill_name for item in detected})
        summaries.append(
            RepoScanSummary(
                repo_id=repo_id,
                source_files=sorted({item.source for item in detected}),
                detected_skills=tech_stack,
            )
        )

        proposed_for_repo: set[str] = set()
        for item in detected:
            normalized = item.skill_name.lower()
            if normalized in existing_skills or normalized in proposed_for_repo:
                continue
            proposals.append(
                SyncProposal(
                    action="add_skill",
                    repo_id=repo_id,
                    value_name=item.skill_name,
                    source=item.source,
                    confidence=item.confidence,
                )
            )
            proposed_for_repo.add(normalized)

        empire_project = empire_projects.get(repo_id)
        if (
            empire_project is not None
            and repo_id.lower() not in existing_projects
            and repo_path.exists()
        ):
            source = "empire.yaml"
            proposals.append(
                SyncProposal(
                    action="add_project",
                    repo_id=repo_id,
                    value_name=repo_id,
                    source=source,
                    confidence=0.9,
                    project_tech_stack=tech_stack,
                    project_description=empire_project.description,
                    project_capability_tags=_build_project_capability_tags(
                        empire_project
                    ),
                    project_url=None,
                )
            )

    return summaries, proposals


def apply_sync_proposals(
    dossier: OperatorDossier,
    proposals: list[SyncProposal],
) -> OperatorDossier:
    existing_skill_names = {
        skill.name.strip().lower()
        for skill in dossier.capabilities.skills
        if skill.name.strip()
    }
    existing_project_names = {
        project.name.strip().lower()
        for project in dossier.capabilities.projects_built
        if project.name.strip()
    }

    for proposal in proposals:
        if proposal.action == "add_skill":
            normalized = proposal.value_name.lower()
            if normalized in existing_skill_names:
                continue
            dossier.capabilities.skills.append(
                Skill(
                    name=proposal.value_name,
                    depth="familiar",
                    recency="active",
                    evidence=f"Detected in {proposal.source}",
                )
            )
            existing_skill_names.add(normalized)
            continue

        if proposal.action == "add_project":
            normalized = proposal.value_name.lower()
            if normalized in existing_project_names:
                continue
            dossier.capabilities.projects_built.append(
                ProjectBuilt(
                    name=proposal.value_name,
                    description=proposal.project_description,
                    tech_stack=proposal.project_tech_stack,
                    capability_tags=proposal.project_capability_tags,
                    url=proposal.project_url,
                )
            )
            existing_project_names.add(normalized)

    return dossier


def scan_repository(repo_path: Path, max_depth: int = 2) -> list[DetectedSkill]:
    detected: list[DetectedSkill] = []
    pyproject_path = repo_path / "pyproject.toml"
    package_json_path = repo_path / "package.json"
    tsconfig_path = repo_path / "tsconfig.json"
    cargo_toml_path = repo_path / "Cargo.toml"
    go_mod_path = repo_path / "go.mod"
    requirements_path = repo_path / "requirements.txt"

    if pyproject_path.exists():
        detected.append(
            DetectedSkill(
                skill_name="Python",
                source=str(pyproject_path),
                confidence=LANGUAGE_CONFIDENCE,
            )
        )
        detected.extend(scan_pyproject_dependencies(pyproject_path))
    elif requirements_path.exists():
        detected.append(
            DetectedSkill(
                skill_name="Python",
                source=str(requirements_path),
                confidence=LANGUAGE_CONFIDENCE,
            )
        )
        detected.extend(scan_requirements_txt(requirements_path))

    if package_json_path.exists():
        language_name = "TypeScript" if tsconfig_path.exists() else "JavaScript"
        detected.append(
            DetectedSkill(
                skill_name=language_name,
                source=str(package_json_path),
                confidence=LANGUAGE_CONFIDENCE,
            )
        )
        detected.extend(scan_package_json_dependencies(package_json_path))

    if cargo_toml_path.exists():
        detected.append(
            DetectedSkill(
                skill_name="Rust",
                source=str(cargo_toml_path),
                confidence=LANGUAGE_CONFIDENCE,
            )
        )
        detected.extend(scan_cargo_toml_dependencies(cargo_toml_path))

    if go_mod_path.exists():
        detected.append(
            DetectedSkill(
                skill_name="Go",
                source=str(go_mod_path),
                confidence=LANGUAGE_CONFIDENCE,
            )
        )
        detected.extend(scan_go_mod_dependencies(go_mod_path))

    # Bounded recursive scan for monorepo sub-packages (depth 1..max_depth)
    _SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", "target"}
    root_manifests = {
        str(pyproject_path), str(requirements_path), str(package_json_path),
        str(cargo_toml_path), str(go_mod_path),
    }

    def _recurse(directory: Path, current_depth: int) -> None:
        if current_depth > max_depth:
            return
        try:
            entries = list(directory.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if not entry.is_dir() or entry.name in _SKIP_DIRS or entry.name.startswith("."):
                continue
            sub_pyproject = entry / "pyproject.toml"
            sub_requirements = entry / "requirements.txt"
            sub_package_json = entry / "package.json"
            sub_tsconfig = entry / "tsconfig.json"
            sub_cargo = entry / "Cargo.toml"
            sub_go_mod = entry / "go.mod"

            if sub_pyproject.exists() and str(sub_pyproject) not in root_manifests:
                detected.append(DetectedSkill(skill_name="Python", source=str(sub_pyproject), confidence=LANGUAGE_CONFIDENCE))
                detected.extend(scan_pyproject_dependencies(sub_pyproject))
            elif sub_requirements.exists() and str(sub_requirements) not in root_manifests:
                detected.append(DetectedSkill(skill_name="Python", source=str(sub_requirements), confidence=LANGUAGE_CONFIDENCE))
                detected.extend(scan_requirements_txt(sub_requirements))

            if sub_package_json.exists() and str(sub_package_json) not in root_manifests:
                lang = "TypeScript" if sub_tsconfig.exists() else "JavaScript"
                detected.append(DetectedSkill(skill_name=lang, source=str(sub_package_json), confidence=LANGUAGE_CONFIDENCE))
                detected.extend(scan_package_json_dependencies(sub_package_json))

            if sub_cargo.exists() and str(sub_cargo) not in root_manifests:
                detected.append(DetectedSkill(skill_name="Rust", source=str(sub_cargo), confidence=LANGUAGE_CONFIDENCE))
                detected.extend(scan_cargo_toml_dependencies(sub_cargo))

            if sub_go_mod.exists() and str(sub_go_mod) not in root_manifests:
                detected.append(DetectedSkill(skill_name="Go", source=str(sub_go_mod), confidence=LANGUAGE_CONFIDENCE))
                detected.extend(scan_go_mod_dependencies(sub_go_mod))

            _recurse(entry, current_depth + 1)

    _recurse(repo_path, 1)

    unique: dict[tuple[str, str], DetectedSkill] = {}
    for item in detected:
        key = (item.skill_name.lower(), item.source)
        previous = unique.get(key)
        if previous is None or item.confidence > previous.confidence:
            unique[key] = item
    return list(unique.values())


def scan_pyproject_dependencies(pyproject_path: Path) -> list[DetectedSkill]:
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)

    detected: list[DetectedSkill] = []
    project = _as_dict(data.get("project"))
    dependency_groups = _as_dict(data.get("dependency-groups"))

    for requirement in _as_list(project.get("dependencies")):
        name = extract_requirement_name(str(requirement))
        if not name:
            continue
        detected.append(
            DetectedSkill(
                skill_name=format_skill_name(name),
                source=str(pyproject_path),
                confidence=RUNTIME_CONFIDENCE,
            )
        )

    for deps in _as_dict(project.get("optional-dependencies")).values():
        for requirement in _as_list(deps):
            name = extract_requirement_name(str(requirement))
            if not name:
                continue
            detected.append(
                DetectedSkill(
                    skill_name=format_skill_name(name),
                    source=str(pyproject_path),
                    confidence=DEV_CONFIDENCE,
                )
            )

    for deps in dependency_groups.values():
        for requirement in _as_list(deps):
            name = extract_requirement_name(str(requirement))
            if not name:
                continue
            detected.append(
                DetectedSkill(
                    skill_name=format_skill_name(name),
                    source=str(pyproject_path),
                    confidence=DEV_CONFIDENCE,
                )
            )

    return detected


def scan_requirements_txt(requirements_path: Path) -> list[DetectedSkill]:
    detected: list[DetectedSkill] = []
    try:
        content = requirements_path.read_text(encoding="utf-8")
    except OSError:
        return detected
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = extract_requirement_name(line)
        if not name:
            continue
        detected.append(
            DetectedSkill(
                skill_name=format_skill_name(name),
                source=str(requirements_path),
                confidence=RUNTIME_CONFIDENCE,
            )
        )
    return detected


def scan_cargo_toml_dependencies(cargo_toml_path: Path) -> list[DetectedSkill]:
    with cargo_toml_path.open("rb") as handle:
        data = tomllib.load(handle)

    detected: list[DetectedSkill] = []
    for section_name, confidence in [
        ("dependencies", RUNTIME_CONFIDENCE),
        ("build-dependencies", DEV_CONFIDENCE),
        ("dev-dependencies", DEV_CONFIDENCE),
    ]:
        for name in _as_dict(data.get(section_name)).keys():
            detected.append(
                DetectedSkill(
                    skill_name=format_skill_name(name),
                    source=str(cargo_toml_path),
                    confidence=confidence,
                )
            )

    for target_config in _as_dict(data.get("target")).values():
        target_dict = _as_dict(target_config)
        for section_name, confidence in [
            ("dependencies", RUNTIME_CONFIDENCE),
            ("build-dependencies", DEV_CONFIDENCE),
            ("dev-dependencies", DEV_CONFIDENCE),
        ]:
            for name in _as_dict(target_dict.get(section_name)).keys():
                detected.append(
                    DetectedSkill(
                        skill_name=format_skill_name(name),
                        source=str(cargo_toml_path),
                        confidence=confidence,
                    )
                )

    return detected


def scan_go_mod_dependencies(go_mod_path: Path) -> list[DetectedSkill]:
    content = go_mod_path.read_text(encoding="utf-8")
    detected: list[DetectedSkill] = []
    in_require_block = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue

        module_path = ""
        confidence = RUNTIME_CONFIDENCE
        if in_require_block:
            module_path = line.split()[0]
        elif line.startswith("require "):
            parts = line.split()
            if len(parts) >= 2:
                module_path = parts[1]
        elif line.startswith("tool "):
            parts = line.split()
            if len(parts) >= 2:
                module_path = parts[1]
                confidence = DEV_CONFIDENCE

        if not module_path:
            continue

        detected.append(
            DetectedSkill(
                skill_name=format_skill_name(_extract_go_module_name(module_path)),
                source=str(go_mod_path),
                confidence=confidence,
            )
        )

    return detected


def scan_package_json_dependencies(package_json_path: Path) -> list[DetectedSkill]:
    with package_json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    detected: list[DetectedSkill] = []

    for key in ("dependencies", "peerDependencies"):
        for name in _as_dict(data.get(key)).keys():
            detected.append(
                DetectedSkill(
                    skill_name=format_skill_name(name),
                    source=str(package_json_path),
                    confidence=RUNTIME_CONFIDENCE,
                )
            )

    for name in _as_dict(data.get("devDependencies")).keys():
        detected.append(
            DetectedSkill(
                skill_name=format_skill_name(name),
                source=str(package_json_path),
                confidence=DEV_CONFIDENCE,
            )
        )

    return detected


def extract_requirement_name(requirement: str) -> str:
    candidate = requirement.split(";", maxsplit=1)[0].strip()
    match = _REQUIREMENT_NAME_RE.match(candidate)
    if not match:
        return ""
    return match.group(1)


def format_skill_name(raw_name: str) -> str:
    normalized = raw_name.strip()
    if not normalized:
        return normalized
    alias = SKILL_ALIASES.get(normalized.lower())
    if alias:
        return alias
    return normalized


def build_theme_suggestions(
    snapshot_texts: list[str],
    existing_tags: list[str],
    limit: int = 5,
) -> list[ThemeSuggestion]:
    existing = {normalize_tag(tag) for tag in existing_tags if str(tag).strip()}
    counts: Counter[str] = Counter()
    samples: dict[str, str] = {}

    for text in snapshot_texts:
        if not text or not text.strip():
            continue
        lowered = text.lower()
        tokens = [
            token
            for token in _TOKEN_RE.findall(lowered)
            if len(token) >= 4 and token not in _STOP_WORDS
        ]
        if not tokens:
            continue

        per_text_tags: set[str] = set()
        for token in tokens:
            per_text_tags.add(normalize_tag(token))
        for left, right in pairwise(tokens):
            if left == right:
                continue
            per_text_tags.add(normalize_tag(f"{left} {right}"))

        for tag in per_text_tags:
            if tag in existing or len(tag) < 4:
                continue
            counts[tag] += 1
            samples.setdefault(tag, text.strip())

    suggestions = [
        ThemeSuggestion(tag=tag, occurrences=count, sample=samples[tag])
        for tag, count in counts.items()
        if count >= 2
    ]
    suggestions.sort(key=lambda item: (-item.occurrences, item.tag))
    return suggestions[:limit]


def _build_project_capability_tags(project: Any) -> list[str]:
    tags = []
    if getattr(project, "domain", "").strip():
        tags.append(normalize_tag(project.domain))
    tags.extend(ROLE_CAPABILITY_TAGS.get(project.role, []))
    return sorted({tag for tag in tags if tag})


def _extract_go_module_name(module_path: str) -> str:
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        return module_path
    candidate = parts[-1]
    if candidate.startswith("v") and candidate[1:].isdigit() and len(parts) > 1:
        candidate = parts[-2]
    return candidate


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
