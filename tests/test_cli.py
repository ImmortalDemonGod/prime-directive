import pytest
from typer.testing import CliRunner
from unittest.mock import patch, Mock, MagicMock, AsyncMock
from prime_directive.bin.pd import app
from omegaconf import OmegaConf

runner = CliRunner()

@pytest.fixture
def mock_config(tmp_path):
    # Use OmegaConf to create a DictConfig that supports dot access
    log_file = tmp_path / "pd.log"
    conf_dict = {
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
            "repo1": {"id": "repo1", "path": "/tmp/repo1", "priority": 10, "active_branch": "main"},
            "repo2": {"id": "repo2", "path": "/tmp/repo2", "priority": 5, "active_branch": "dev"}
        }
    }
    return OmegaConf.create(conf_dict)

@patch("prime_directive.bin.pd.load_config")
def test_list_command(mock_load, mock_config):
    mock_load.return_value = mock_config
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "repo1" in result.stdout
    assert "repo2" in result.stdout
    assert "10" in result.stdout  # Priority

@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.get_status")
@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_session")
@patch("prime_directive.bin.pd.dispose_engine", new_callable=AsyncMock)
def test_status_command(mock_dispose, mock_get_session, mock_init_db, mock_get_status, mock_load, mock_config):
    mock_load.return_value = mock_config
    
    # Mock get_status return values
    mock_get_status.return_value = {
        "branch": "main",
        "is_dirty": False,
        "uncommitted_files": [],
        "diff_stat": ""
    }
    
    # Mock DB Session
    mock_session = AsyncMock()
    # Mock result for snapshot query
    mock_snapshot = MagicMock()
    mock_snapshot.timestamp.strftime.return_value = "2025-01-01 12:00"
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_snapshot
    
    # Make execute return the result (AsyncMock automatically makes it awaitable if we configure it right, 
    # but strictly execute returns a coroutine. AsyncMock calls return coroutines.)
    mock_session.execute.return_value = mock_result 
    
    # Define async generator for get_session
    async def async_gen(_db_path=None):
        yield mock_session
    
    # side_effect needs to be the function itself if it's a generator? 
    # Or calling the mock returns the generator object.
    # When `get_session()` is called, it returns an async iterator.
    # `async_gen()` returns an async generator.
    mock_get_session.side_effect = async_gen

    result = runner.invoke(app, ["status"], catch_exceptions=False)
    
    assert result.exit_code == 0
    assert "Prime Directive Status" in result.stdout
    assert "repo1" in result.stdout
    assert "Clean" in result.stdout
    assert "2025-01-01 12:00" in result.stdout
    
    # Verify cleanup
    mock_dispose.assert_called_once()

@patch("prime_directive.bin.pd.load_config")
@patch("shutil.which")
@patch("requests.get")
@patch("os.path.exists")
def test_doctor_command(mock_exists, mock_get, mock_which, mock_load, mock_config):
    mock_load.return_value = mock_config
    
    # Mock shutil.which
    def which_side_effect(cmd):
        if cmd == "tmux":
            return "/usr/bin/tmux"
        if cmd == "code":
            return "/usr/bin/code"
        return None
    mock_which.side_effect = which_side_effect
    
    # Mock requests.get (Ollama)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "gpt-4:latest"}]} # Matches mock_config model
    mock_get.return_value = mock_response
    
    # Mock os.path.exists
    mock_exists.return_value = True

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Prime Directive Doctor" in result.stdout
    assert "Tmux Installed" in result.stdout
    assert "✅" in result.stdout
