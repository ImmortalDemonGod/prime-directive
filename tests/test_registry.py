import pytest
import yaml
from pathlib import Path
from prime_directive.core.registry import load_registry, Registry, RepoConfig


def test_load_registry_success(tmp_path):
    # Create a temporary registry file
    registry_content = """
    system:
      editor_cmd: "code"
      ai_model: "gpt-4"
      db_path: "/tmp/test.db"
    
    repos:
      test-repo:
        id: "test-repo"
        path: "/tmp/test-repo"
        priority: 5
        active_branch: "main"
    """
    config_file = tmp_path / "registry.yaml"
    config_file.write_text(registry_content)

    registry = load_registry(str(config_file))

    assert registry.system.editor_cmd == "code"
    assert registry.system.ai_model == "gpt-4"
    assert "test-repo" in registry.repos
    assert registry.repos["test-repo"].path == "/tmp/test-repo"
    assert registry.repos["test-repo"].priority == 5


def test_load_registry_defaults():
    # Test loading with non-existent file should return defaults
    registry = load_registry("non_existent_file.yaml")

    assert registry.system.editor_cmd == "windsurf"
    assert registry.system.ai_model == "qwen2.5-coder"
    assert registry.repos == {}


def test_repo_config_validation():
    # Test that RepoConfig validation works
    with pytest.raises(Exception):
        # Missing required field 'path' (pydantic validation)
        RepoConfig(id="fail", priority=1)
