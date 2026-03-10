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
        return {
            StrategicWeight.CRITICAL.value: 4,
            StrategicWeight.HIGH.value: 3,
            StrategicWeight.MEDIUM.value: 2,
            StrategicWeight.LOW.value: 1,
        }[self.strategic_weight.value]


@dataclass(frozen=True)
class EmpireConfig:
    version: str
    projects: dict[str, EmpireProject]


def get_empire_path() -> Path:
    return Path.home() / ".prime-directive" / "empire.yaml"


def load_empire_if_exists(cfg: Any, path: Optional[Path] = None) -> Optional[EmpireConfig]:
    target_path = path or get_empire_path()
    if not target_path.exists():
        return None
    return load_empire_config(cfg, target_path)


def load_empire_config(cfg: Any, path: Optional[Path] = None) -> EmpireConfig:
    target_path = path or get_empire_path()
    with target_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Empire config must be a mapping: {target_path}")
    return parse_empire_config(raw_data, cfg)


def parse_empire_config(raw_data: dict[str, Any], cfg: Any) -> EmpireConfig:
    version = str(raw_data.get("version", "")).strip()
    if version != "3.0":
        raise ValueError(f'Invalid empire version: expected "3.0", got {version!r}')

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
            raise ValueError(f"Empire project `{project_id}` must be a mapping")

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
            raise ValueError(f"Empire project `{project_id}` field `depends_on` must be a list")

        projects[project_id] = EmpireProject(
            id=project_id,
            domain=str(raw_project.get("domain", "")).strip(),
            role=role,
            strategic_weight=strategic_weight,
            description=str(raw_project.get("description", "")).strip(),
            depends_on=[str(item).strip() for item in depends_on if str(item).strip()],
        )

    project_ids = set(projects.keys())
    for project in projects.values():
        invalid_deps = [item for item in project.depends_on if item not in project_ids]
        if invalid_deps:
            raise ValueError(
                f"Empire project `{project.id}` has invalid depends_on entries: {', '.join(invalid_deps)}"
            )

    cycle = _find_cycle(projects)
    if cycle:
        raise ValueError(f"Empire dependency graph contains a cycle: {' -> '.join(cycle)}")

    return EmpireConfig(version=version, projects=projects)


def _find_cycle(projects: dict[str, EmpireProject]) -> list[str]:
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        if node in active:
            start = stack.index(node)
            return stack[start:] + [node]
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
