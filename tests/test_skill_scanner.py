from unittest.mock import patch

from omegaconf import OmegaConf
from typer.testing import CliRunner

from prime_directive.bin.pd import app
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

    summaries, proposals = build_sync_proposals(cfg, dossier)

    assert len(summaries) == 1
    assert summaries[0].repo_id == "repo1"
    assert any(item.action == "add_skill" and item.value_name == "httpx" for item in proposals)
    assert any(item.action == "add_skill" and item.value_name == "SQLModel" for item in proposals)
    assert any(item.action == "add_project" and item.value_name == "repo1" for item in proposals)
    assert not any(item.action == "add_skill" and item.value_name == "Python" for item in proposals)


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
            "system": {"db_path": ":memory:", "log_path": str(tmp_path / "pd.log")},
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

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path), patch(
        "prime_directive.bin.pd.load_config", return_value=cfg
    ):
        result = runner.invoke(app, ["dossier", "sync-skills"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Operator Dossier Skill Sync" in result.stdout
    assert "httpx" in result.stdout
    assert "Dry run only" in result.stdout


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
            "system": {"db_path": ":memory:", "log_path": str(tmp_path / "pd.log")},
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

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path), patch(
        "prime_directive.bin.pd.load_config", return_value=cfg
    ):
        result = runner.invoke(
            app,
            ["dossier", "sync-skills", "--apply"],
            catch_exceptions=False,
        )

    loaded = load_operator_dossier(dossier_path)
    skill_names = {skill.name for skill in loaded.capabilities.skills}
    project_names = {project.name for project in loaded.capabilities.projects_built}

    assert result.exit_code == 0
    assert "Applied" in result.stdout
    assert "TypeScript" in skill_names
    assert "Next.js" in skill_names
    assert "repo1" in project_names


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
            "system": {"db_path": ":memory:", "log_path": str(tmp_path / "pd.log")},
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

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path), patch(
        "prime_directive.bin.pd.load_config", return_value=cfg
    ), patch(
        "prime_directive.bin.pd._load_recent_snapshot_texts",
        return_value=[
            "Investigating gradient debugging for diffusion training instability.",
            "Need gradient debugging and diffusion training fixes before next run.",
            "Documented diffusion training blocker after more gradient debugging.",
        ],
    ):
        result = runner.invoke(
            app,
            ["dossier", "sync-skills", "--deep", "--apply"],
            catch_exceptions=False,
        )

    loaded = load_operator_dossier(dossier_path)

    assert result.exit_code == 0
    assert "Deep Theme Suggestions" in result.stdout
    assert loaded.capabilities.domain_expertise
