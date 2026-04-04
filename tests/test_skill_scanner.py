from unittest.mock import AsyncMock, patch

from omegaconf import OmegaConf
from typer.testing import CliRunner

from prime_directive.bin.pd import app
from prime_directive.core.dossier_ai import AIAnalysisMetadata
from prime_directive.core.empire import (
    EmpireConfig,
    EmpireProject,
    ProjectRole,
    StrategicWeight,
)
from prime_directive.core.identity import (
    default_operator_dossier,
    load_operator_dossier,
    Skill,
    write_operator_dossier,
)
from prime_directive.core.skill_scanner import (
    build_sync_proposals,
    build_theme_suggestions,
    scan_repository,
    ThemeSuggestion,
)

runner = CliRunner()


def test_scan_repository_detects_python_dependencies(tmp_path):
    repo_path = tmp_path / "python_repo"
    repo_path.mkdir()
    (repo_path / "pyproject.toml").write_text(
        """
[project]
name = "python-repo"
dependencies = ["httpx>=0.27.0", "sqlmodel>=0.0.27"]

[project.optional-dependencies]
test = ["pytest>=8"]
""".strip(),
        encoding="utf-8",
    )

    detected = scan_repository(repo_path)
    skill_names = {item.skill_name for item in detected}

    assert "Python" in skill_names
    assert "httpx" in skill_names
    assert "SQLModel" in skill_names
    assert "pytest" in skill_names


def test_scan_repository_detects_typescript_dependencies(tmp_path):
    repo_path = tmp_path / "ts_repo"
    repo_path.mkdir()
    (repo_path / "package.json").write_text(
        '{"dependencies":{"next":"14.0.0","react":"18.0.0"},"devDependencies":{"typescript":"5.0.0","prisma":"5.0.0"}}',
        encoding="utf-8",
    )
    (repo_path / "tsconfig.json").write_text("{}", encoding="utf-8")

    detected = scan_repository(repo_path)
    skill_names = {item.skill_name for item in detected}

    assert "TypeScript" in skill_names
    assert "Next.js" in skill_names
    assert "React" in skill_names
    assert "Prisma" in skill_names


def test_scan_repository_detects_rust_and_go_dependencies(tmp_path):
    rust_repo = tmp_path / "rust_repo"
    rust_repo.mkdir()
    (rust_repo / "Cargo.toml").write_text(
        """
[package]
name = "rust-repo"
version = "0.1.0"

[dependencies]
serde = "1.0"

[dev-dependencies]
tokio = "1.0"
""".strip(),
        encoding="utf-8",
    )

    go_repo = tmp_path / "go_repo"
    go_repo.mkdir()
    (go_repo / "go.mod").write_text(
        """
module example.com/demo

go 1.22

require (
    github.com/gin-gonic/gin v1.10.0
    golang.org/x/tools v0.22.0
)
""".strip(),
        encoding="utf-8",
    )

    rust_detected = scan_repository(rust_repo)
    go_detected = scan_repository(go_repo)

    rust_skills = {item.skill_name for item in rust_detected}
    go_skills = {item.skill_name for item in go_detected}

    assert "Rust" in rust_skills
    assert "serde" in rust_skills
    assert "tokio" in rust_skills
    assert "Go" in go_skills
    assert "gin" in go_skills
    assert "tools" in go_skills


def test_build_sync_proposals_adds_only_missing_skills_and_projects(tmp_path):
    python_repo = tmp_path / "repo1"
    python_repo.mkdir()
    (python_repo / "pyproject.toml").write_text(
        """
[project]
name = "repo1"
dependencies = ["httpx>=0.27.0", "sqlmodel>=0.0.27"]
""".strip(),
        encoding="utf-8",
    )

    cfg = OmegaConf.create(
        {
            "repos": {
                "repo1": {
                    "id": "repo1",
                    "path": str(python_repo),
                    "priority": 10,
                    "active_branch": "main",
                }
            }
        }
    )
    dossier = default_operator_dossier()
    dossier.capabilities.skills.append(
        Skill(
            name="Python",
            depth="expert",
            recency="active",
            evidence="existing",
        )
    )

    empire = EmpireConfig(
        version="3.0",
        projects={
            "repo1": EmpireProject(
                id="repo1",
                domain="developer-tooling",
                role=ProjectRole.INFRASTRUCTURE,
                strategic_weight=StrategicWeight.HIGH,
                description="Repo 1 description",
                depends_on=[],
            )
        },
    )

    with patch(
        "prime_directive.core.skill_scanner.load_empire_if_exists",
        return_value=empire,
    ):
        summaries, proposals = build_sync_proposals(cfg, dossier)

    assert len(summaries) == 1
    assert summaries[0].repo_id == "repo1"
    assert any(
        item.action == "add_skill" and item.value_name == "httpx"
        for item in proposals
    )
    assert any(
        item.action == "add_skill" and item.value_name == "SQLModel"
        for item in proposals
    )
    assert any(
        item.action == "add_project" and item.value_name == "repo1"
        for item in proposals
    )
    assert not any(
        item.action == "add_skill" and item.value_name == "Python"
        for item in proposals
    )
    project_proposal = next(
        item for item in proposals if item.action == "add_project"
    )
    assert project_proposal.project_description == "Repo 1 description"
    assert "developer-tooling" in project_proposal.project_capability_tags
    assert "infrastructure" in project_proposal.project_capability_tags


def test_dossier_sync_skills_dry_run_reports_proposals(tmp_path):
    repo_path = tmp_path / "repo1"
    repo_path.mkdir()
    (repo_path / "pyproject.toml").write_text(
        """
[project]
name = "repo1"
dependencies = ["httpx>=0.27.0"]
""".strip(),
        encoding="utf-8",
    )

    cfg = OmegaConf.create(
        {
            "system": {
                "db_path": ":memory:",
                "log_path": str(tmp_path / "pd.log"),
            },
            "repos": {
                "repo1": {
                    "id": "repo1",
                    "path": str(repo_path),
                    "priority": 10,
                    "active_branch": "main",
                }
            },
        }
    )

    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)
    empire = EmpireConfig(
        version="3.0",
        projects={
            "repo1": EmpireProject(
                id="repo1",
                domain="full-stack",
                role=ProjectRole.EXPERIMENTAL,
                strategic_weight=StrategicWeight.MEDIUM,
                description="Repo 1 description",
                depends_on=[],
            )
        },
    )

    with (
        patch(
            "prime_directive.core.identity.Path.home", return_value=tmp_path
        ),
        patch("prime_directive.bin.pd.load_config", return_value=cfg),
        patch(
            "prime_directive.core.skill_scanner.load_empire_if_exists",
            return_value=empire,
        ),
    ):
        result = runner.invoke(
            app, ["dossier", "sync-skills"], catch_exceptions=False
        )

    loaded = load_operator_dossier(dossier_path)

    assert result.exit_code == 0
    assert "Operator Dossier Skill Sync" in result.stdout
    assert "httpx" in result.stdout
    assert "repo1" in result.stdout
    assert "Dry run only" in result.stdout
    assert loaded.capabilities.skills == []
    assert loaded.capabilities.projects_built == []


def test_dossier_sync_skills_apply_persists_changes(tmp_path):
    repo_path = tmp_path / "repo1"
    repo_path.mkdir()
    (repo_path / "package.json").write_text(
        '{"dependencies":{"next":"14.0.0"}}',
        encoding="utf-8",
    )
    (repo_path / "tsconfig.json").write_text("{}", encoding="utf-8")

    cfg = OmegaConf.create(
        {
            "system": {
                "db_path": ":memory:",
                "log_path": str(tmp_path / "pd.log"),
            },
            "repos": {
                "repo1": {
                    "id": "repo1",
                    "path": str(repo_path),
                    "priority": 10,
                    "active_branch": "main",
                }
            },
        }
    )

    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)
    empire = EmpireConfig(
        version="3.0",
        projects={
            "repo1": EmpireProject(
                id="repo1",
                domain="full-stack",
                role=ProjectRole.EXPERIMENTAL,
                strategic_weight=StrategicWeight.MEDIUM,
                description="Repo 1 description",
                depends_on=[],
            )
        },
    )

    with (
        patch(
            "prime_directive.core.identity.Path.home", return_value=tmp_path
        ),
        patch("prime_directive.bin.pd.load_config", return_value=cfg),
        patch(
            "prime_directive.core.skill_scanner.load_empire_if_exists",
            return_value=empire,
        ),
    ):
        result = runner.invoke(
            app,
            ["dossier", "sync-skills", "--apply"],
            catch_exceptions=False,
        )

    loaded = load_operator_dossier(dossier_path)
    skill_names = {skill.name for skill in loaded.capabilities.skills}
    project_names = {
        project.name for project in loaded.capabilities.projects_built
    }

    assert result.exit_code == 0
    assert "Applied" in result.stdout
    assert "TypeScript" in skill_names
    assert "Next.js" in skill_names
    assert "repo1" in project_names
    project = next(
        project
        for project in loaded.capabilities.projects_built
        if project.name == "repo1"
    )
    assert project.description == "Repo 1 description"
    assert "full-stack" in project.capability_tags
    assert "experimental" in project.capability_tags


def test_dossier_sync_skills_rejects_apply_and_dry_run_together(tmp_path):
    repo_path = tmp_path / "repo1"
    repo_path.mkdir()
    (repo_path / "pyproject.toml").write_text(
        """
[project]
name = "repo1"
dependencies = ["httpx>=0.27.0"]
""".strip(),
        encoding="utf-8",
    )

    cfg = OmegaConf.create(
        {
            "system": {
                "db_path": ":memory:",
                "log_path": str(tmp_path / "pd.log"),
            },
            "repos": {
                "repo1": {
                    "id": "repo1",
                    "path": str(repo_path),
                    "priority": 10,
                    "active_branch": "main",
                }
            },
        }
    )

    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)

    with (
        patch(
            "prime_directive.core.identity.Path.home", return_value=tmp_path
        ),
        patch("prime_directive.bin.pd.load_config", return_value=cfg),
    ):
        result = runner.invoke(
            app,
            ["dossier", "sync-skills", "--apply", "--dry-run"],
        )

    assert result.exit_code != 0
    assert "--apply` and `--dry-run` cannot be used together" in result.output


def test_build_theme_suggestions_extracts_repeated_snapshot_themes():
    snapshot_texts = [
        "Investigating gradient debugging for diffusion training instability.",
        "Need gradient debugging and diffusion training fixes before next run.",
        "Documented diffusion training blocker after more gradient debugging.",
    ]

    suggestions = build_theme_suggestions(snapshot_texts, existing_tags=[])
    tags = {item.tag for item in suggestions}

    assert "gradient" in tags or "gradient-debugging" in tags
    assert "diffusion-training" in tags or "diffusion" in tags


def test_dossier_sync_skills_deep_apply_adds_theme_suggestions(tmp_path):
    repo_path = tmp_path / "repo1"
    repo_path.mkdir()
    (repo_path / "pyproject.toml").write_text(
        """
[project]
name = "repo1"
dependencies = ["httpx>=0.27.0"]
""".strip(),
        encoding="utf-8",
    )

    cfg = OmegaConf.create(
        {
            "system": {
                "db_path": ":memory:",
                "log_path": str(tmp_path / "pd.log"),
            },
            "repos": {
                "repo1": {
                    "id": "repo1",
                    "path": str(repo_path),
                    "priority": 10,
                    "active_branch": "main",
                }
            },
        }
    )

    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)

    with (
        patch(
            "prime_directive.core.identity.Path.home", return_value=tmp_path
        ),
        patch("prime_directive.bin.pd.load_config", return_value=cfg),
        patch(
            "prime_directive.bin.pd._load_recent_snapshot_texts",
            return_value=(
                [
                    "Investigating gradient debugging for diffusion training instability.",
                    "Need gradient debugging and diffusion training fixes before next run.",
                    "Documented diffusion training blocker after more gradient debugging.",
                ],
                3,
                1,
            ),
        ),
        patch(
            "prime_directive.bin.pd.generate_theme_suggestions_with_ai",
            new_callable=AsyncMock,
            return_value=(
                [
                    ThemeSuggestion(
                        tag="gradient-debugging",
                        occurrences=3,
                        sample="3 snapshots mention gradient debugging",
                        confidence=0.7,
                    )
                ],
                AIAnalysisMetadata(
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=120,
                    output_tokens=30,
                    cost_estimate_usd=0.0001,
                ),
                None,
            ),
        ),
    ):
        result = runner.invoke(
            app,
            ["dossier", "sync-skills", "--deep", "--apply"],
            catch_exceptions=False,
        )

    loaded = load_operator_dossier(dossier_path)

    assert result.exit_code == 0
    assert "Deep Analysis (LLM)" in result.stdout
    assert "gradient-debugging" in result.stdout
    assert loaded.capabilities.domain_expertise
