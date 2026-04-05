from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml


class ProjectRole(str, Enum):
    RESEARCH = "RESEARCH"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    MAINTENANCE = "MAINTENANCE"
    EXPERIMENTAL = "EXPERIMENTAL"


class StrategicWeight(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


WEIGHT_NUMERIC_MAP = {
    StrategicWeight.CRITICAL: 4,
    StrategicWeight.HIGH: 3,
    StrategicWeight.MEDIUM: 2,
    StrategicWeight.LOW: 1,
}


@dataclass(frozen=True)
class EmpireProject:
    id: str
    domain: str
    role: ProjectRole
    strategic_weight: StrategicWeight
    description: str
    depends_on: list[str] = field(default_factory=list)

    @property
    def weight_numeric(self) -> int:
        """
        Get the numeric score for the project's strategic weight.
        
        Returns:
            int: Integer score corresponding to `self.strategic_weight` (CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1).
        """
        return WEIGHT_NUMERIC_MAP[self.strategic_weight]


@dataclass(frozen=True)
class EmpireConfig:
    version: str
    projects: dict[str, EmpireProject]


def get_empire_path() -> Path:
    """
    Get the default path to the Empire configuration file.
    
    Returns:
        path (Path): Path to the user's ~/.prime-directive/empire.yaml file. This function does not check for the file's existence.
    """
    return Path.home() / ".prime-directive" / "empire.yaml"


def load_empire_if_exists(
    cfg: Any, path: Optional[Path] = None
) -> Optional[EmpireConfig]:
    """
    Load the Empire configuration from the specified path if the file exists.
    
    Parameters:
    	cfg (Any): Application configuration used during parsing and validation (e.g., supplies known repository ids).
    	path (Optional[Path]): Path to the empire YAML file; if omitted, the default path (~/.prime-directive/empire.yaml) is used.
    
    Returns:
    	An EmpireConfig parsed from the file, or `None` if the target file does not exist.
    """
    target_path = path or get_empire_path()
    if not target_path.exists():
        return None
    return load_empire_config(cfg, target_path)


def load_empire_config(cfg: Any, path: Optional[Path] = None) -> EmpireConfig:
    """
    Load and validate an Empire configuration from the given file and return an EmpireConfig.
    
    Parameters:
        cfg (Any): Runtime configuration object used to validate project references (e.g., provides `repos`).
        path (Optional[Path]): Path to the empire YAML file; if omitted, the default user empire path is used.
    
    Returns:
        EmpireConfig: Parsed and validated Empire configuration.
    
    Raises:
        ValueError: If the top-level YAML value is not a mapping, or if parsing/validation of the configuration fails.
    """
    target_path = path or get_empire_path()
    with target_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Empire config must be a mapping: {target_path}")
    return parse_empire_config(raw_data, cfg)


def parse_empire_config(raw_data: dict[str, Any], cfg: Any) -> EmpireConfig:
    """
    Parse and validate a raw Empire YAML mapping and convert it into an EmpireConfig.
    
    Parses the top-level mapping produced by yaml.safe_load and enforces the Empire schema:
    - Requires `version` to equal "3.0".
    - Requires a `projects` mapping and validates each project's shape.
    - Verifies each project id exists in `cfg.repos`.
    - Validates `role` and `strategic_weight` against their enums.
    - Normalizes `domain`, `description`, and `depends_on` entries (stripping and filtering empty values).
    - Ensures every dependency refers to a known project and that the dependency graph contains no cycles.
    
    Parameters:
        raw_data (dict[str, Any]): Top-level mapping loaded from empire.yaml.
        cfg (Any): Application configuration object whose `repos` mapping provides valid project ids.
    
    Returns:
        EmpireConfig: A validated, immutable configuration containing `version` and normalized `projects`.
    
    Raises:
        ValueError: If the version is not "3.0", if `projects` is missing or malformed, if any project id is not present in `cfg.repos`, if project fields are the wrong type or contain invalid enum values, if `depends_on` contains unknown ids, or if a dependency cycle is detected.
    """
    version = str(raw_data.get("version", "")).strip()
    if version != "3.0":
        raise ValueError(
            f'Invalid empire version: expected "3.0", got {version!r}'
        )

    raw_projects = raw_data.get("projects")
    if not isinstance(raw_projects, dict):
        raise ValueError("Empire config field `projects` must be a mapping")

    config_repo_ids = set(getattr(cfg, "repos", {}).keys())
    projects: dict[str, EmpireProject] = {}

    for project_id, raw_project in raw_projects.items():
        if project_id not in config_repo_ids:
            raise ValueError(
                f"Empire project `{project_id}` is not present in config.yaml repos"
            )
        if not isinstance(raw_project, dict):
            raise ValueError(
                f"Empire project `{project_id}` must be a mapping"
            )

        role_value = str(raw_project.get("role", "")).strip()
        weight_value = str(raw_project.get("strategic_weight", "")).strip()
        try:
            role = ProjectRole(role_value)
        except ValueError as exc:
            valid = ", ".join(item.value for item in ProjectRole)
            raise ValueError(
                f"Empire project `{project_id}` has invalid role {role_value!r}; expected one of {valid}"
            ) from exc
        try:
            strategic_weight = StrategicWeight(weight_value)
        except ValueError as exc:
            valid = ", ".join(item.value for item in StrategicWeight)
            raise ValueError(
                f"Empire project `{project_id}` has invalid strategic_weight {weight_value!r}; expected one of {valid}"
            ) from exc

        depends_on = raw_project.get("depends_on", [])
        if not isinstance(depends_on, list):
            raise ValueError(
                f"Empire project `{project_id}` field `depends_on` must be a list"
            )

        projects[project_id] = EmpireProject(
            id=project_id,
            domain=str(raw_project.get("domain", "")).strip(),
            role=role,
            strategic_weight=strategic_weight,
            description=str(raw_project.get("description", "")).strip(),
            depends_on=[
                str(item).strip() for item in depends_on if str(item).strip()
            ],
        )

    project_ids = set(projects.keys())
    for project in projects.values():
        invalid_deps = [
            item for item in project.depends_on if item not in project_ids
        ]
        if invalid_deps:
            raise ValueError(
                f"Empire project `{project.id}` has invalid depends_on entries: {', '.join(invalid_deps)}"
            )

    cycle = _find_cycle(projects)
    if cycle:
        raise ValueError(
            f"Empire dependency graph contains a cycle: {' -> '.join(cycle)}"
        )

    return EmpireConfig(version=version, projects=projects)


def _find_cycle(projects: dict[str, EmpireProject]) -> list[str]:
    """
    Finds a circular dependency among the provided projects.
    
    Parameters:
        projects (dict[str, EmpireProject]): Mapping of project id to EmpireProject whose `depends_on` lists define dependency edges.
    
    Returns:
        cycle (list[str]): Ordered list of project ids forming the detected cycle, starting and ending with the same id to close the loop; empty list if no cycle exists.
    """
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        """
        Visit a project node and detect any dependency cycle reachable from that node.
        
        Parameters:
            node (str): The project id to start the traversal from.
        
        Returns:
            list[str]: A list of project ids describing the detected cycle, with the final element repeating the first to close the cycle (e.g., ['a', 'b', 'a']); an empty list if no cycle is found.
        """
        if node in active:
            start = stack.index(node)
            return [*stack[start:], node]
        if node in visited:
            return []

        visited.add(node)
        active.add(node)
        stack.append(node)
        for dependency in projects[node].depends_on:
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        active.remove(node)
        return []

    for project_id in projects:
        cycle = visit(project_id)
        if cycle:
            return cycle
    return []
