import pytest
from omegaconf import OmegaConf

from prime_directive.core.empire import (
    ProjectRole,
    StrategicWeight,
    load_empire_config,
)


def test_load_empire_config_accepts_valid_overlay(tmp_path):
    cfg = OmegaConf.create(
        {
            "repos": {
                "repo1": {"id": "repo1", "path": "/tmp/repo1", "priority": 10},
                "repo2": {"id": "repo2", "path": "/tmp/repo2", "priority": 5},
            }
        }
    )
    empire_path = tmp_path / "empire.yaml"
    empire_path.write_text(
        """
version: "3.0"
projects:
  repo1:
    domain: "developer-tooling"
    role: "INFRASTRUCTURE"
    strategic_weight: "HIGH"
    description: "Repo 1 description"
    depends_on: []
  repo2:
    domain: "research"
    role: "RESEARCH"
    strategic_weight: "CRITICAL"
    description: "Repo 2 description"
    depends_on:
      - repo1
""".strip(),
        encoding="utf-8",
    )

    loaded = load_empire_config(cfg, empire_path)

    assert loaded.version == "3.0"
    assert loaded.projects["repo1"].role == ProjectRole.INFRASTRUCTURE
    assert loaded.projects["repo2"].strategic_weight == StrategicWeight.CRITICAL
    assert loaded.projects["repo2"].depends_on == ["repo1"]


def test_load_empire_config_rejects_unknown_repo_id(tmp_path):
    cfg = OmegaConf.create(
        {"repos": {"repo1": {"id": "repo1", "path": "/tmp/repo1", "priority": 10}}}
    )
    empire_path = tmp_path / "empire.yaml"
    empire_path.write_text(
        """
version: "3.0"
projects:
  repo2:
    domain: "developer-tooling"
    role: "INFRASTRUCTURE"
    strategic_weight: "HIGH"
    description: "Repo 2 description"
    depends_on: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        load_empire_config(cfg, empire_path)

    assert "not present in config.yaml repos" in str(excinfo.value)


def test_load_empire_config_rejects_cycles(tmp_path):
    cfg = OmegaConf.create(
        {
            "repos": {
                "repo1": {"id": "repo1", "path": "/tmp/repo1", "priority": 10},
                "repo2": {"id": "repo2", "path": "/tmp/repo2", "priority": 5},
            }
        }
    )
    empire_path = tmp_path / "empire.yaml"
    empire_path.write_text(
        """
version: "3.0"
projects:
  repo1:
    domain: "developer-tooling"
    role: "INFRASTRUCTURE"
    strategic_weight: "HIGH"
    description: "Repo 1 description"
    depends_on:
      - repo2
  repo2:
    domain: "research"
    role: "RESEARCH"
    strategic_weight: "CRITICAL"
    description: "Repo 2 description"
    depends_on:
      - repo1
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contains a cycle"):
        load_empire_config(cfg, empire_path)
