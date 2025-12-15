import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock, call
from prime_directive.bin.pd import app
from prime_directive.core.orchestrator import detect_current_repo_id
from omegaconf import OmegaConf
from datetime import datetime

runner = CliRunner()

@pytest.fixture
def mock_config(tmp_path):
    log_file = tmp_path / "pd.log"
    return OmegaConf.create({
        "system": {
            "editor_cmd": "code", 
            "ai_model": "gpt-4", 
            "ai_fallback_provider": "none",
            "ai_fallback_model": "gpt-4o-mini",
            "ai_require_confirmation": True,
            "openai_api_url": "https://api.openai.com/v1/chat/completions",
            "openai_timeout_seconds": 10.0,
            "openai_max_tokens": 150,
            "ollama_api_url": "http://localhost:11434/api/generate",
            "ollama_timeout_seconds": 5.0,
            "ollama_max_retries": 0,
            "ollama_backoff_seconds": 0.0,
            "db_path": ":memory:",
            "log_path": str(log_file),
            "mock_mode": False
        },
        "repos": {
            "current-repo": {"id": "current-repo", "path": "/tmp/current-repo", "priority": 10, "active_branch": "main"},
            "target-repo": {"id": "target-repo", "path": "/tmp/target-repo", "priority": 5, "active_branch": "dev"}
        }
    })

@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.run_switch")
def test_switch_command(mock_run_switch, mock_load, mock_config):
    mock_load.return_value = mock_config

    result = runner.invoke(app, ["switch", "target-repo"])
    
    assert result.exit_code == 0

    mock_run_switch.assert_called_once()
    args, kwargs = mock_run_switch.call_args
    assert args[0] == "target-repo"
    assert args[1] == mock_config
    assert "cwd" in kwargs
    assert "freeze_fn" in kwargs
    assert "ensure_session_fn" in kwargs
    assert "launch_editor_fn" in kwargs
    assert "init_db_fn" in kwargs
    assert "get_session_fn" in kwargs
    assert "dispose_engine_fn" in kwargs
    assert "console" in kwargs
    assert "logger" in kwargs


def test_detect_current_repo_id_prefers_longest_prefix():
    repos = {
        "outer": {"path": "/tmp/work"},
        "inner": {"path": "/tmp/work/project"},
    }
    cwd = "/tmp/work/project/subdir"
    assert detect_current_repo_id(cwd, repos) == "inner"

@patch("prime_directive.bin.pd.load_config")
def test_switch_invalid_repo(mock_load, mock_config):
    mock_load.return_value = mock_config
    result = runner.invoke(app, ["switch", "invalid-repo"])
    assert result.exit_code == 1
    assert "Repository 'invalid-repo' not found" in result.stdout
