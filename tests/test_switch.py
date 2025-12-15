import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock, call
from prime_directive.bin.pd import app
from prime_directive.core.orchestrator import detect_current_repo_id, switch_logic
from omegaconf import OmegaConf
from datetime import datetime
import logging

from prime_directive.core.db import EventLog, EventType

runner = CliRunner()


@pytest.fixture
def mock_config(tmp_path):
    log_file = tmp_path / "pd.log"
    return OmegaConf.create(
        {
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
                "mock_mode": False,
            },
            "repos": {
                "current-repo": {
                    "id": "current-repo",
                    "path": "/tmp/current-repo",
                    "priority": 10,
                    "active_branch": "main",
                },
                "target-repo": {
                    "id": "target-repo",
                    "path": "/tmp/target-repo",
                    "priority": 5,
                    "active_branch": "dev",
                },
            },
        }
    )


@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.run_switch")
def test_switch_command(mock_run_switch, mock_load, mock_config):
    mock_load.return_value = mock_config
    mock_run_switch.return_value = False

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


@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.run_switch")
def test_switch_command_shell_attach_exit_code(
    mock_run_switch, mock_load, mock_config
):
    mock_load.return_value = mock_config
    mock_run_switch.return_value = True

    result = runner.invoke(app, ["switch", "target-repo"])
    assert result.exit_code == 88


def test_detect_current_repo_id_prefers_longest_prefix():
    repos = {
        "outer": {"path": "/tmp/work"},
        "inner": {"path": "/tmp/work/project"},
    }
    cwd = "/tmp/work/project/subdir"
    assert detect_current_repo_id(cwd, repos) == "inner"


@pytest.mark.asyncio
async def test_switch_logic_logs_switch_in_event(tmp_path):
    cfg = OmegaConf.create(
        {
            "system": {
                "mock_mode": True,
                "db_path": str(tmp_path / "test.db"),
                "editor_cmd": "code",
            },
            "repos": {
                "target-repo": {
                    "id": "target-repo",
                    "path": "/tmp/target-repo",
                    "priority": 1,
                    "active_branch": "main",
                }
            },
        }
    )

    freeze_fn = AsyncMock()
    ensure_session_fn = MagicMock()
    launch_editor_fn = MagicMock()
    init_db_fn = AsyncMock()
    dispose_engine_fn = AsyncMock()
    console = MagicMock()
    logger = logging.getLogger("test")

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    async def get_session_fn(_db_path: str):
        yield session

    await switch_logic(
        "target-repo",
        cfg,
        cwd=str(tmp_path),
        freeze_fn=freeze_fn,
        ensure_session_fn=ensure_session_fn,
        launch_editor_fn=launch_editor_fn,
        init_db_fn=init_db_fn,
        get_session_fn=get_session_fn,
        dispose_engine_fn=dispose_engine_fn,
        console=console,
        logger=logger,
    )

    init_db_fn.assert_awaited_once()
    session.commit.assert_awaited()
    assert session.add.called

    added_obj = session.add.call_args[0][0]
    assert isinstance(added_obj, EventLog)
    assert added_obj.repo_id == "target-repo"
    assert added_obj.event_type == EventType.SWITCH_IN


@patch("prime_directive.bin.pd.load_config")
def test_switch_invalid_repo(mock_load, mock_config):
    mock_load.return_value = mock_config
    result = runner.invoke(app, ["switch", "invalid-repo"])
    assert result.exit_code == 1
    assert "Repository 'invalid-repo' not found" in result.stdout
