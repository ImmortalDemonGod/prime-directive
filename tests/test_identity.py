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
                        {
                            "title": "T",
                            "venue": "V",
                            "year": 2025,
                            "tags": ["AI Safety"],
                        }
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
            "system": {
                "db_path": ":memory:",
                "log_path": str(tmp_path / "pd.log"),
            },
            "repos": {},
        }
    )
    with (
        patch(
            "prime_directive.core.identity.Path.home", return_value=tmp_path
        ),
        patch("prime_directive.core.empire.Path.home", return_value=tmp_path),
        patch("prime_directive.bin.pd.load_config", return_value=cfg),
    ):
        result = runner.invoke(
            app, ["dossier", "init"], catch_exceptions=False
        )

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

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app, ["dossier", "init"], catch_exceptions=False
        )

    assert result.exit_code == 1
    assert "Dossier already exists" in result.stdout


def test_dossier_validate_reports_success_for_valid_file(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    write_operator_dossier(default_operator_dossier(), dossier_path)

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app, ["dossier", "validate"], catch_exceptions=False
        )

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

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app, ["dossier", "validate"], catch_exceptions=False
        )

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
    assert (
        "verification-over-trust" in dossier.connection_surface.philosophy_tags
    )


def test_dossier_sync_tags_updates_connection_surface(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.identity.formative_experiences = ["Open source career pivot"]
    dossier.capabilities.domain_expertise = ["developer-tooling"]
    dossier.connection_surface.philosophy_tags = ["ownership"]
    write_operator_dossier(dossier, dossier_path)

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app, ["dossier", "sync-tags"], catch_exceptions=False
        )

    loaded = load_operator_dossier(dossier_path)

    assert result.exit_code == 0
    assert (
        "Tag Sync — Deriving connection_surface from Layers 1-4"
        in result.stdout
    )
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

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app, ["dossier", "show", "--tags-only"], catch_exceptions=False
        )

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

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app, ["dossier", "show", "--layer", "2"], catch_exceptions=False
        )

    assert result.exit_code == 0
    assert (
        "Operator Dossier — Layer 2: Technical Capabilities" in result.stdout
    )
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

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
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
    dossier.positioning.positioning_statement = (
        "Verification-first systems builder"
    )
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    write_operator_dossier(dossier, dossier_path)

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
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
    assert exported["capabilities"]["domain_expertise"] == [
        "developer-tooling"
    ]
    assert exported["connection_surface"]["topic_tags"] == [
        "developer-tooling"
    ]


def test_dossier_export_yaml_to_file(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    export_path = tmp_path / "exports" / "dossier.yaml"
    dossier = default_operator_dossier()
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    write_operator_dossier(dossier, dossier_path)

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
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
    assert exported["connection_surface"]["topic_tags"] == [
        "developer-tooling"
    ]


def test_dossier_export_tags_only_to_stdout(tmp_path):
    dossier_dir = tmp_path / ".prime-directive"
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "operator_dossier.yaml"
    dossier = default_operator_dossier()
    dossier.connection_surface.topic_tags = ["developer-tooling"]
    dossier.connection_surface.philosophy_tags = ["verification-over-trust"]
    write_operator_dossier(dossier, dossier_path)

    with patch(
        "prime_directive.core.identity.Path.home", return_value=tmp_path
    ):
        result = runner.invoke(
            app,
            ["dossier", "export", "--format", "tags-only"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert "topic_tags: developer-tooling" in result.stdout
    assert "philosophy_tags: verification-over-trust" in result.stdout


import pytest

from prime_directive.core.identity import (
    migrate_operator_dossier,
    validate_operator_dossier_data,
)


# ── migrate_operator_dossier ──


def test_migrate_operator_dossier_v30_to_v31():
    raw = {"version": "3.0", "identity": {}, "capabilities": {}}
    result = migrate_operator_dossier(raw)
    assert result["version"] == "3.1"
    assert result is raw


def test_migrate_operator_dossier_v31_is_noop():
    raw = {"version": "3.1"}
    result = migrate_operator_dossier(raw)
    assert result["version"] == "3.1"


def test_migrate_operator_dossier_unsupported_version_raises():
    with pytest.raises(
        ValueError, match="Cannot migrate dossier from version '2.0'"
    ):
        migrate_operator_dossier({"version": "2.0"})


def test_migrate_operator_dossier_empty_version_raises():
    with pytest.raises(ValueError, match="Cannot migrate"):
        migrate_operator_dossier({})


# ── validate_operator_dossier_data: auto-migration ──


def test_validate_auto_migrates_v30_dossier():
    raw = {
        "version": "3.0",
        "identity": {},
        "capabilities": {},
        "network": {},
        "positioning": {},
        "connection_surface": {},
    }
    report = validate_operator_dossier_data(raw)
    assert raw["version"] == "3.1"
    assert not any("Invalid dossier version" in e for e in report.errors)


def test_validate_handles_yaml_float_version():
    raw = {
        "version": 3.1,
        "identity": {},
        "capabilities": {},
        "network": {},
        "positioning": {},
        "connection_surface": {},
    }
    report = validate_operator_dossier_data(raw)
    assert raw["version"] == "3.1"
    assert not any("Invalid dossier version" in e for e in report.errors)


def test_validate_handles_yaml_int_version():
    raw = {
        "version": 3,
        "identity": {},
        "capabilities": {},
        "network": {},
        "positioning": {},
        "connection_surface": {},
    }
    report = validate_operator_dossier_data(raw)
    assert any("Cannot migrate" in e for e in report.errors)


def test_validate_handles_yaml_float_v30():
    raw = {
        "version": 3.0,
        "identity": {},
        "capabilities": {},
        "network": {},
        "positioning": {},
        "connection_surface": {},
    }
    report = validate_operator_dossier_data(raw)
    assert raw["version"] == "3.1"
    assert not any("Invalid dossier version" in e for e in report.errors)


def test_validate_unsupported_version_records_both_errors():
    raw = {
        "version": "1.0",
        "identity": {},
        "capabilities": {},
        "network": {},
        "positioning": {},
        "connection_surface": {},
    }
    report = validate_operator_dossier_data(raw)
    assert any("Cannot migrate" in e for e in report.errors)
    assert any("Invalid dossier version" in e for e in report.errors)
