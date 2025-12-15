import pytest
from typer.testing import CliRunner
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from prime_directive.bin.pd import app
from omegaconf import OmegaConf

runner = CliRunner()


@pytest.fixture
def mock_config(tmp_path):
    log_file = tmp_path / "pd.log"
    return OmegaConf.create(
        {
            "system": {
                "editor_cmd": "code",
                "ai_model": "gpt-4",
                "ai_provider": "ollama",
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
                "test-repo": {
                    "id": "test-repo",
                    "path": "/tmp/test-repo",
                    "priority": 10,
                    "active_branch": "main",
                }
            },
        }
    )


@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.get_status", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.capture_terminal_state", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_active_task")
@patch("prime_directive.bin.pd.generate_sitrep", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_session")  # Mocking the async generator
def test_freeze_command(
    mock_get_session,
    mock_init_db,
    mock_generate_sitrep,
    mock_get_active_task,
    mock_capture_terminal,
    mock_get_status,
    mock_load,
    mock_config,
):
    mock_load.return_value = mock_config

    # Mock Git
    mock_get_status.return_value = {
        "branch": "main",
        "is_dirty": True,
        "uncommitted_files": ["file.py"],
        "diff_stat": "file.py | 1 +",
    }

    # Mock Terminal
    mock_capture_terminal.return_value = ("ls", "file.py")

    # Mock Task
    mock_get_active_task.return_value = {
        "id": 1,
        "title": "Fix Bug",
        "status": "in-progress",
    }

    # Mock Scribe
    mock_generate_sitrep.return_value = "SITREP: Fixed bug."

    # Mock DB Session
    mock_session = AsyncMock()
    # session.add is synchronous in SQLAlchemy
    mock_session.add = Mock()
    # Mock execute for repository check - return empty result (repo doesn't exist)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    # async generator mock
    async def async_gen(_db_path=None):
        yield mock_session

    mock_get_session.side_effect = async_gen

    result = runner.invoke(
        app, ["freeze", "test-repo", "--note", "Testing freeze command"]
    )

    assert result.exit_code == 0
    assert "Freezing context for test-repo" in result.stdout
    assert "Generating AI SITREP" in result.stdout
    assert "Snapshot saved" in result.stdout
    assert "SITREP: Fixed bug." in result.stdout
    assert "YOUR NOTE:" in result.stdout

    # Verify DB calls - now adds Repository first, then ContextSnapshot
    assert mock_session.add.call_count >= 1
    # Get the last add call which should be the snapshot
    snapshot = mock_session.add.call_args_list[-1][0][0]
    assert snapshot.repo_id == "test-repo"
    assert snapshot.human_note == "Testing freeze command"

    mock_init_db.assert_awaited_once()


@patch("prime_directive.bin.pd.load_config")
def test_freeze_command_invalid_repo(mock_load, mock_config):
    mock_load.return_value = mock_config
    result = runner.invoke(
        app, ["freeze", "invalid-repo", "--note", "Testing invalid repo"]
    )
    assert result.exit_code == 1
    assert "Repository 'invalid-repo' not found" in result.stdout
