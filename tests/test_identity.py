import json
from unittest.mock import patch
from omegaconf import OmegaConf
import yaml
from typer.testing import CliRunner

from prime_directive.bin.pd import app
from prime_directive.core.identity import (
    ProjectBuilt,
    Skill,
    default_operator_dossier,
    GeographicEntry,
    load_operator_dossier,
    sync_connection_surface,
    validate_operator_dossier_file,
    write_operator_dossier,
)

runner = CliRunner()


def test_default_operator_dossier_validates(tmp_path):
    dossier = default_operator_dossier()
    dossier_path = tmp_path / "operator_dossier.yaml"

    write_operator_dossier(dossier, dossier_path)
    report, raw_data = validate_operator_dossier_file(dossier_path)
    loaded = load_operator_dossier(dossier_path)

    assert report.errors == []
    assert raw_data["version"] == "3.1"
    assert loaded.version == "3.1"
    assert "identity is empty" in report.info
    assert "connection_surface.philosophy_tags is empty" in report.info


def test_validate_operator_dossier_file_rejects_invalid_skill_enum(tmp_path):
    dossier_path = tmp_path / "operator_dossier.yaml"
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.1",
                "identity": {},
                "capabilities": {
                    "skills": [
                        {
                            "name": "Python",
                            "depth": "legendary",
                            "recency": "active",
                            "evidence": "test",
                        }
                    ]
                },
                "network": {},
                "positioning": {},
                "connection_surface": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report, _raw_data = validate_operator_dossier_file(dossier_path)

    assert report.errors
    assert "capabilities.skills[0].depth" in report.errors[0]


def test_validate_operator_dossier_file_warns_on_non_normalized_tags(tmp_path):
    dossier_path = tmp_path / "operator_dossier.yaml"
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.1",
                "identity": {
                    "publications": [
                        {"title": "T", "venue": "V", "year": 2025, "tags": ["AI Safety"]}
                    ]
                },
                "capabilities": {
                    "domain_expertise": ["ML Pipeline"],
                    "skills": [],
                    "projects_built": [
                        {
                            "name": "proj",
                            "description": "desc",
                            "tech_stack": [],
                            "capability_tags": ["Agent Safety"],
                        }
                    ],
                },
                "network": {},
                "positioning": {},
                "connection_surface": {"topic_tags": ["Code Quality"]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report, _raw_data = validate_operator_dossier_file(dossier_path)

    assert report.errors == []
    assert report.warnings
    assert any("non-normalized tag" in item for item in report.warnings)


def test_dossier_init_creates_file(tmp_path):
    cfg = OmegaConf.create(
        {
            "system": {"db_path": ":memory:", "log_path": str(tmp_path / "pd.log")},
            "repos": {},
        }
    )
    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path), patch(
        "prime_directive.bin.pd.load_config", return_value=cfg
    ):
        result = runner.invoke(app, ["dossier", "init"], catch_exceptions=False)

    dossier_path = tmp_path / ".prime-directive" / "operator_dossier.yaml"

    assert result.exit_code == 0
    assert dossier_path.exists()
    data = yaml.safe_load(dossier_path.read_text(encoding="utf-8"))
    assert data["version"] == "3.1"
    assert "PRIME DIRECTIVE — Operator Dossier Setup" in result.stdout
    assert "Skeleton written to" in result.stdout
    assert "Auto-populated:" in result.stdout


def test_dossier_init_without_force_refuses_overwrite(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["dossier", "init"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "Dossier already exists" in result.stdout


def test_dossier_validate_reports_success_for_valid_file(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["dossier", "validate"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Validation passed" in result.stdout
    assert str(dossier_path) in result.stdout


def test_dossier_validate_reports_failure_for_invalid_file(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.1",
                "identity": {},
                "capabilities": {
                    "skills": [
                        {
                            "name": "Python",
                            "depth": "bad",
                            "recency": "ancient",
                        }
                    ]
                },
                "network": {},
                "positioning": {},
                "connection_surface": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["dossier", "validate"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "Validation failed" in result.stdout
    assert "capabilities.skills[0].depth" in result.stdout
    assert "capabilities.skills[0].recency" in result.stdout


def test_sync_connection_surface_derives_expected_tags():
    dossier = default_operator_dossier()
    dossier.identity.formative_experiences = [
        "Career pivot from hardware to software",
        "Became self-taught after no formal CS program",
        "Built an open source tool",
    ]
    dossier.identity.hobbies = ["Technical Writing", "Backpacking"]
    dossier.identity.geographic_history = [
        GeographicEntry(location="San Francisco, CA", years="2020-present")
    ]
    dossier.identity.values = ["Verification over trust"]
    dossier.connection_surface.philosophy_tags = ["Verification Over Trust"]
    dossier.capabilities.domain_expertise = ["developer-tooling"]

    sync_connection_surface(dossier)

    assert "career-pivot" in dossier.connection_surface.experience_tags
    assert "self-taught" in dossier.connection_surface.experience_tags
    assert "open-source" in dossier.connection_surface.experience_tags
    assert "developer-tooling" in dossier.connection_surface.topic_tags
    assert "san-francisco-ca" in dossier.connection_surface.geographic_tags
    assert "technical-writing" in dossier.connection_surface.hobby_tags
    assert "verification-over-trust" in dossier.connection_surface.philosophy_tags


def test_dossier_sync_tags_updates_connection_surface(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.identity.formative_experiences = ["Open source career pivot"]
    dossier.capabilities.domain_expertise = ["developer-tooling"]
    dossier.connection_surface.philosophy_tags = ["ownership"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["dossier", "sync-tags"], catch_exceptions=False)

    loaded = load_operator_dossier(dossier_path)

    assert result.exit_code == 0
    assert "Tag Sync — Deriving connection_surface from Layers 1-4" in result.stdout
    assert "Updated" in result.stdout
    assert "developer-tooling" in loaded.connection_surface.topic_tags
    assert "open-source" in loaded.connection_surface.experience_tags
    assert "ownership" in loaded.connection_surface.philosophy_tags


def test_dossier_show_tags_only_outputs_tag_table(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["dossier", "show", "--tags-only"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Operator Connection Surface (Layer 5)" in result.stdout
    assert "developer-tooling" in result.stdout
    assert "Total tags:" in result.stdout


def test_dossier_show_layer_2_outputs_rich_capabilities_view(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.capabilities.skills = [
        Skill(
            name="Python",
            depth="expert",
            recency="active",
            evidence="Detected in pyproject.toml",
        )
    ]
    dossier.capabilities.domain_expertise = ["developer-tooling"]
    dossier.capabilities.projects_built = [
        ProjectBuilt(
            name="prime-directive",
            description="CLI tool for context preservation",
            tech_stack=["Python", "Typer"],
            capability_tags=["developer-tooling", "infrastructure"],
            url=None,
        )
    ]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["dossier", "show", "--layer", "2"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Operator Dossier — Layer 2: Technical Capabilities" in result.stdout
    assert "Skills (1)" in result.stdout
    assert "developer-tooling" in result.stdout
    assert "prime-directive" in result.stdout
    assert "Capability Tags" in result.stdout


def test_dossier_export_layer5_only_json_to_stdout(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(
            app,
            ["dossier", "export", "--format", "json", "--layer5-only"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert '"connection_surface"' in result.stdout
    assert '"developer-tooling"' in result.stdout
    assert '"identity"' not in result.stdout


def test_dossier_export_full_json_matches_black_box_contract_shape(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.identity.values = ["verification-over-trust"]
    dossier.capabilities.domain_expertise = ["developer-tooling"]
    dossier.network.industries = ["devtools"]
    dossier.positioning.positioning_statement = "Verification-first systems builder"
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(
            app,
            ["dossier", "export", "--format", "json"],
            catch_exceptions=False,
        )

    exported = json.loads(result.stdout)

    assert result.exit_code == 0
    assert exported["version"] == "3.1"
    assert set(exported.keys()) == {
        "version",
        "identity",
        "capabilities",
        "network",
        "positioning",
        "connection_surface",
    }
    assert exported["capabilities"]["domain_expertise"] == ["developer-tooling"]
    assert exported["connection_surface"]["topic_tags"] == ["developer-tooling"]


def test_dossier_export_yaml_to_file(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    export_path = tmp_path / "exports" / "dossier.yaml"
    dossier = default_operator_dossier()
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(
            app,
            [
                "dossier",
                "export",
                "--format",
                "yaml",
                "--output",
                str(export_path),
            ],
            catch_exceptions=False,
        )

    exported = yaml.safe_load(export_path.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert export_path.exists()
    assert exported["connection_surface"]["topic_tags"] == ["developer-tooling"]


def test_dossier_export_tags_only_to_stdout(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    dossier.connection_surface.philosophy_tags = ["verification-over-trust"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(
            app,
            ["dossier", "export", "--format", "tags-only"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert "topic_tags: developer-tooling" in result.stdout
    assert "philosophy_tags: verification-over-trust" in result.stdout


def test_normalize_tag_handles_edge_cases():
    """Test tag normalization handles various edge cases correctly."""
    from prime_directive.core.identity import normalize_tag

    assert normalize_tag("AI Safety") == "ai-safety"
    assert normalize_tag("ML_Pipeline") == "ml-pipeline"
    assert normalize_tag("Code/Quality") == "code-quality"
    assert normalize_tag("  Multiple   Spaces  ") == "multiple-spaces"
    assert normalize_tag("UPPERCASE") == "uppercase"
    assert normalize_tag("under_score") == "under-score"
    assert normalize_tag("Mixed_Case-Combo") == "mixed-case-combo"
    assert normalize_tag("dash--double") == "dash-double"
    assert normalize_tag("") == ""


def test_validate_operator_dossier_detects_duplicate_tags(tmp_path):
    """Test that validation warns about duplicate tags in lists."""
    dossier_path = tmp_path / "operator_dossier.yaml"
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.1",
                "identity": {},
                "capabilities": {
                    "domain_expertise": ["developer-tooling", "developer-tooling"]
                },
                "network": {},
                "positioning": {},
                "connection_surface": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report, _raw_data = validate_operator_dossier_file(dossier_path)

    assert any("duplicate tag" in item.lower() for item in report.warnings)


def test_validate_operator_dossier_warns_tech_stack_missing_skill(tmp_path):
    """Test validation warns when tech_stack has no matching skill entry."""
    dossier_path = tmp_path / "operator_dossier.yaml"
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.1",
                "identity": {},
                "capabilities": {
                    "skills": [],
                    "projects_built": [
                        {
                            "name": "project1",
                            "description": "test",
                            "tech_stack": ["Python", "Django"],
                            "capability_tags": [],
                        }
                    ],
                },
                "network": {},
                "positioning": {},
                "connection_surface": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report, _raw_data = validate_operator_dossier_file(dossier_path)

    assert any("no matching skill" in item for item in report.warnings)
    assert any("Python" in item for item in report.warnings)
    assert any("Django" in item for item in report.warnings)


def test_validate_operator_dossier_warns_excessive_tags(tmp_path):
    """Test validation warns when tag lists exceed 50 items."""
    dossier_path = tmp_path / "operator_dossier.yaml"
    many_tags = [f"tag-{i}" for i in range(51)]
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "3.1",
                "identity": {},
                "capabilities": {},
                "network": {},
                "positioning": {},
                "connection_surface": {"topic_tags": many_tags},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    report, _raw_data = validate_operator_dossier_file(dossier_path)

    assert any("more than 50 tags" in item for item in report.warnings)


def test_sync_connection_surface_preserves_philosophy_tags():
    """Test that sync_connection_surface preserves manually-set philosophy tags."""
    dossier = default_operator_dossier()
    dossier.connection_surface.philosophy_tags = [
        "Verification Over Trust",
        "ownership",
    ]
    dossier.capabilities.domain_expertise = ["developer-tooling"]

    sync_connection_surface(dossier)

    assert "verification-over-trust" in dossier.connection_surface.philosophy_tags
    assert "ownership" in dossier.connection_surface.philosophy_tags


def test_sync_connection_surface_deduplicates_tags():
    """Test that sync_connection_surface removes duplicates from derived tags."""
    dossier = default_operator_dossier()
    dossier.capabilities.domain_expertise = [
        "developer-tooling",
        "Developer-Tooling",
    ]
    dossier.capabilities.projects_built = [
        ProjectBuilt(
            name="proj1",
            description="test",
            tech_stack=[],
            capability_tags=["developer-tooling"],
        )
    ]

    sync_connection_surface(dossier)

    assert dossier.connection_surface.topic_tags.count("developer-tooling") == 1


def test_load_operator_dossier_rejects_wrong_version(tmp_path):
    """Test that loading a dossier with wrong version fails."""
    dossier_path = tmp_path / "operator_dossier.yaml"
    dossier_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.0",
                "identity": {},
                "capabilities": {},
                "network": {},
                "positioning": {},
                "connection_surface": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    try:
        load_operator_dossier(dossier_path)
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        assert "version" in str(exc).lower()


def test_dossier_validate_offers_tag_normalization_fixes(tmp_path):
    """Test that validate command offers to apply tag normalization fixes."""
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.capabilities.domain_expertise = ["ML Pipeline", "AI Safety"]
    write_operator_dossier(dossier, dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(
            app,
            ["dossier", "validate"],
            catch_exceptions=False,
            input="n\n",
        )

    assert result.exit_code == 0
    assert "Tag normalization fixes available" in result.stdout
    assert "ML Pipeline" in result.stdout


def test_dossier_export_with_empty_connection_surface(tmp_path):
    """Test exporting a dossier with empty connection surface."""
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)

    with patch("prime_directive.core.identity.Path.home", return_value=tmp_path):
        result = runner.invoke(
            app,
            ["dossier", "export", "--format", "json", "--layer5-only"],
            catch_exceptions=False,
        )

    exported = json.loads(result.stdout)

    assert result.exit_code == 0
    assert exported["version"] == "3.1"
    assert all(
        len(exported["connection_surface"][key]) == 0
        for key in [
            "experience_tags",
            "topic_tags",
            "geographic_tags",
            "education_tags",
            "industry_tags",
            "hobby_tags",
            "philosophy_tags",
        ]
    )