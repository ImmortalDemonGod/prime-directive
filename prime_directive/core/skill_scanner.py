from __future__ import annotations

import logging
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

logger = logging.getLogger("prime_directive")

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
    """
    Builds scan summaries and synchronization proposals by scanning repositories configured in `cfg` and comparing detected capabilities against `dossier`.

    Scans each repo path in `cfg.repos` to detect languages and dependencies, produces a RepoScanSummary per repository, and emits SyncProposal entries for new skills and (when present in an external empire config) for new projects. Repositories that fail scanning are skipped with a warning. Duplicate skill proposals are avoided both against the dossier and within the same repository scan.

    Parameters:
        cfg (Any): Configuration object containing a mapping `repos` of repository identifiers to repo configuration (must provide a `path` attribute).
        dossier (OperatorDossier): Operator dossier whose existing capabilities (skills and projects_built) are used to suppress already-known proposals.

    Returns:
        tuple[list[RepoScanSummary], list[SyncProposal]]:
            - A list of per-repository scan summaries.
            - A list of synchronization proposals to add detected skills or projects.
    """
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
    proposed_skills: set[str] = set()
    try:
        empire = load_empire_if_exists(cfg)
    except Exception as exc:
        logger.warning("Could not load empire.yaml: %s", exc)
        empire = None
    empire_projects = empire.projects if empire is not None else {}

    for repo_id, repo_cfg in cfg.repos.items():
        repo_path = Path(str(repo_cfg.path)).expanduser()
        try:
            detected = scan_repository(repo_path)
        except (OSError, ValueError) as exc:
            logger.warning("Skipping repo %s: scan failed: %s", repo_id, exc)
            continue
        tech_stack = sorted({item.skill_name for item in detected})
        summaries.append(
            RepoScanSummary(
                repo_id=repo_id,
                source_files=sorted({item.source for item in detected}),
                detected_skills=tech_stack,
            )
        )

        for item in detected:
            normalized = item.skill_name.lower()
            if normalized in existing_skills or normalized in proposed_skills:
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
            proposed_skills.add(normalized)

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
    """
    Apply synchronization proposals to an OperatorDossier by adding any missing skills or projects.

    Parameters:
        dossier (OperatorDossier): The dossier to mutate; skills and projects will be appended when proposals require them.
        proposals (list[SyncProposal]): Sync proposals to apply. Proposals with `action == "add_skill"` will add a Skill
            (depth set to "familiar", recency set to "active", evidence set to "Detected in <source>") if the skill name
            does not already exist in the dossier (case-insensitive). Proposals with `action == "add_project"` will add a
            ProjectBuilt if the project name does not already exist in the dossier (case-insensitive).

    Returns:
        OperatorDossier: The same dossier instance after applying non-duplicate proposals.
    """
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


def scan_repository(
    repo_path: Path, max_depth: int = 2
) -> list[DetectedSkill]:
    """
    Scan a repository for programming languages and dependency-based skills, returning detected items for sync proposals.

    Performs a bounded scan of the repository rooted at `repo_path`, detecting language manifests (pyproject.toml, requirements.txt, package.json/tsconfig.json, Cargo.toml, go.mod) and extracting dependency names as `DetectedSkill` entries. The scan recurses into subdirectories up to `max_depth` levels to discover monorepo sub-packages while skipping common vendor/build directories. Duplicate detections are collapsed by (skill name lowercased, source) keeping the entry with the highest confidence.

    Parameters:
        repo_path (Path): Path to the repository root to scan.
        max_depth (int): Maximum recursion depth for subdirectory scanning (default 2).

    Returns:
        list[DetectedSkill]: A list of unique detected skills, each with `skill_name`, `source` (manifest path), and `confidence`.
    """
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
    if requirements_path.exists():
        if not pyproject_path.exists():
            detected.append(
                DetectedSkill(
                    skill_name="Python",
                    source=str(requirements_path),
                    confidence=LANGUAGE_CONFIDENCE,
                )
            )
        detected.extend(scan_requirements_txt(requirements_path))

    if package_json_path.exists():
        language_name = (
            "TypeScript" if tsconfig_path.exists() else "JavaScript"
        )
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
    _SKIP_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
    }
    root_manifests = {
        str(pyproject_path),
        str(requirements_path),
        str(package_json_path),
        str(cargo_toml_path),
        str(go_mod_path),
    }

    def _recurse(directory: Path, current_depth: int) -> None:
        """
        Recursively scan a directory tree for language manifest files and dependency lists, appending discovered DetectedSkill entries to the enclosing `detected` list until the configured `max_depth` is exceeded.

        Parameters:
            directory (Path): Directory to scan.
            current_depth (int): Current recursion depth relative to the initial root (incremented on each recursion).

        Notes:
            - The function silently returns on PermissionError when listing a directory.
            - Scanning stops when `current_depth > max_depth`.
        """
        if current_depth > max_depth:
            return
        try:
            entries = list(directory.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if (
                not entry.is_dir()
                or entry.name in _SKIP_DIRS
                or entry.name.startswith(".")
            ):
                continue
            sub_pyproject = entry / "pyproject.toml"
            sub_requirements = entry / "requirements.txt"
            sub_package_json = entry / "package.json"
            sub_tsconfig = entry / "tsconfig.json"
            sub_cargo = entry / "Cargo.toml"
            sub_go_mod = entry / "go.mod"

            if (
                sub_pyproject.exists()
                and str(sub_pyproject) not in root_manifests
            ):
                detected.append(
                    DetectedSkill(
                        skill_name="Python",
                        source=str(sub_pyproject),
                        confidence=LANGUAGE_CONFIDENCE,
                    )
                )
                detected.extend(scan_pyproject_dependencies(sub_pyproject))
            elif (
                sub_requirements.exists()
                and str(sub_requirements) not in root_manifests
            ):
                detected.append(
                    DetectedSkill(
                        skill_name="Python",
                        source=str(sub_requirements),
                        confidence=LANGUAGE_CONFIDENCE,
                    )
                )
                detected.extend(scan_requirements_txt(sub_requirements))

            if (
                sub_package_json.exists()
                and str(sub_package_json) not in root_manifests
            ):
                lang = "TypeScript" if sub_tsconfig.exists() else "JavaScript"
                detected.append(
                    DetectedSkill(
                        skill_name=lang,
                        source=str(sub_package_json),
                        confidence=LANGUAGE_CONFIDENCE,
                    )
                )
                detected.extend(
                    scan_package_json_dependencies(sub_package_json)
                )

            if sub_cargo.exists() and str(sub_cargo) not in root_manifests:
                detected.append(
                    DetectedSkill(
                        skill_name="Rust",
                        source=str(sub_cargo),
                        confidence=LANGUAGE_CONFIDENCE,
                    )
                )
                detected.extend(scan_cargo_toml_dependencies(sub_cargo))

            if sub_go_mod.exists() and str(sub_go_mod) not in root_manifests:
                detected.append(
                    DetectedSkill(
                        skill_name="Go",
                        source=str(sub_go_mod),
                        confidence=LANGUAGE_CONFIDENCE,
                    )
                )
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
    """
    Extract dependency names from a pyproject.toml and produce DetectedSkill entries for each dependency.

    Parses the `project.dependencies`, `project.optional-dependencies`, and top-level `dependency-groups` sections of the specified pyproject.toml and emits a DetectedSkill for every parsed requirement name. Dependencies listed under `project.dependencies` are assigned runtime confidence; dependencies from `project.optional-dependencies` and `dependency-groups` are assigned development confidence.

    Parameters:
        pyproject_path (Path): Path to the pyproject.toml file to scan.

    Returns:
        list[DetectedSkill]: DetectedSkill objects for each discovered dependency. Entries from `project.dependencies` use `RUNTIME_CONFIDENCE`; entries from `project.optional-dependencies` and `dependency-groups` use `DEV_CONFIDENCE`.
    """
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
    """
    Extract dependency names from a requirements.txt file into DetectedSkill entries.

    Skips blank lines, lines beginning with `#`, and lines beginning with `-`. If the file cannot be read, returns an empty list.

    Parameters:
        requirements_path (Path): Path to the requirements.txt file to parse.

    Returns:
        list[DetectedSkill]: One DetectedSkill per parsed dependency with `skill_name` normalized via `format_skill_name`, `source` set to the file path string, and `confidence` set to `RUNTIME_CONFIDENCE`.
    """
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
    """
    Scan a Cargo.toml file for dependency entries and produce DetectedSkill records.

    Parameters:
        cargo_toml_path (Path): Path to the Cargo.toml file to scan.

    Returns:
        list[DetectedSkill]: A list of detected dependencies where each item has:
            - `skill_name`: the normalized dependency name,
            - `source`: the string path of `cargo_toml_path`,
            - `confidence`: `RUNTIME_CONFIDENCE` for entries from `dependencies`,
              `DEV_CONFIDENCE` for `build-dependencies` and `dev-dependencies`.
            Dependencies declared under `target.*` sections are included with the same confidence mapping.
    """
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
    """
    Extract module dependencies from a go.mod file into DetectedSkill records.

    Parses require blocks, single-line `require` directives, and `tool` directives to extract module paths. Each found module is converted into a normalized skill name via `_extract_go_module_name` and `format_skill_name`. `tool` directives are marked with `DEV_CONFIDENCE`; other requires use `RUNTIME_CONFIDENCE`.

    Parameters:
        go_mod_path (Path): Path to the go.mod file to parse.

    Returns:
        list[DetectedSkill]: A list of DetectedSkill objects representing each discovered module dependency.
    """
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
                skill_name=format_skill_name(
                    _extract_go_module_name(module_path)
                ),
                source=str(go_mod_path),
                confidence=confidence,
            )
        )

    return detected


def scan_package_json_dependencies(
    package_json_path: Path,
) -> list[DetectedSkill]:
    """
    Scan a package.json file and extract detected dependency names as skills.

    Parameters:
        package_json_path (Path): Path to the package.json file to scan.

    Returns:
        list[DetectedSkill]: Detected skills for each dependency key in the file. Entries for
        `dependencies` and `peerDependencies` use runtime confidence; entries for
        `devDependencies` use development confidence. Each skill's `skill_name` is normalized
        and `source` is set to the provided file path.
    """
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
    """
    Extract the leading package or requirement identifier from a requirement specifier.

    Parses the requirement up to any environment marker (';') and returns the first identifier
    matching the requirement-name pattern; returns an empty string if no valid name is found.

    Parameters:
        requirement (str): A requirement specifier (for example "package>=1.2; python_version<'3.9'").

    Returns:
        str: The extracted requirement name, or an empty string if none is present.
    """
    candidate = requirement.split(";", maxsplit=1)[0].strip()
    match = _REQUIREMENT_NAME_RE.match(candidate)
    if not match:
        return ""
    return match.group(1)


def format_skill_name(raw_name: str) -> str:
    """
    Normalize a raw dependency or package name into a canonical, display-friendly skill name.

    Trims surrounding whitespace and, if the trimmed name matches a known alias (case-insensitive),
    returns the canonical display name from SKILL_ALIASES; otherwise returns the trimmed input.

    Returns:
        normalized_name (str): Empty string if the input is empty after trimming; otherwise the canonical
        name if an alias exists, or the trimmed original name.
    """
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
    """
    Suggest theme tag candidates derived from provided snapshot texts.

    Analyzes the input texts to propose tags (single tokens and adjacent bigrams) that are not present in `existing_tags`, counts how many distinct texts mention each candidate, and returns the most frequent candidates that appear in at least two different texts.

    Parameters:
        snapshot_texts (list[str]): Text snippets to analyze for candidate tags.
        existing_tags (list[str]): Tags to exclude from suggestions; values are normalized before comparison.
        limit (int): Maximum number of suggestions to return.

    Returns:
        list[ThemeSuggestion]: Up to `limit` suggestions sorted by descending occurrence then tag; each suggestion appears only if its candidate occurs in two or more distinct input texts.
    """
    existing = {
        normalize_tag(tag) for tag in existing_tags if str(tag).strip()
    }
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
    """
    Builds capability tags for a project based on its domain and role.

    Parameters:
        project (Any): An object expected to have a `domain` attribute (string) and a `role` attribute; `domain` is normalized into a tag if non-empty and `role` is used to look up role-specific tags.

    Returns:
        list[str]: A sorted list of unique, non-empty capability tags derived from the project's domain and role.
    """
    tags = []
    if getattr(project, "domain", "").strip():
        tags.append(normalize_tag(project.domain))
    tags.extend(ROLE_CAPABILITY_TAGS.get(project.role, []))
    return sorted({tag for tag in tags if tag})


def _extract_go_module_name(module_path: str) -> str:
    """
    Select the most appropriate package name from a Go module import path.

    Parameters:
        module_path (str): The full module path (for example "github.com/user/repo" or "github.com/user/repo/v2").

    Returns:
        str: The chosen module name segment — normally the last path component, or the penultimate component if the last component is a semantic version token like "v2". If the input is empty or contains no non-empty segments, returns the original `module_path`.
    """
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        return module_path
    candidate = parts[-1]
    if (
        candidate.startswith("v")
        and candidate[1:].isdigit()
        and len(parts) > 1
    ):
        candidate = parts[-2]
    return candidate


def _as_dict(value: Any) -> dict[str, Any]:
    """
    Normalize an arbitrary value to a dictionary.

    Parameters:
        value (Any): The value to normalize.

    Returns:
        dict[str, Any]: The original `value` if it is a `dict`, otherwise an empty dictionary.
    """
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """
    Return the input unchanged if it is a list, otherwise return an empty list.

    Parameters:
        value (Any): Value to ensure is a list.

    Returns:
        list[Any]: `value` if it is a `list`, otherwise an empty list.
    """
    return value if isinstance(value, list) else []
