import pytest
from typer.testing import CliRunner
from unittest.mock import patch, Mock, MagicMock
from prime_directive.bin.pd import app
from prime_directive.core.registry import Registry, RepoConfig, SystemConfig

runner = CliRunner()

@pytest.fixture
def mock_registry():
    return Registry(
        system=SystemConfig(editor_cmd="code", ai_model="gpt-4"),
        repos={
            "repo1": RepoConfig(id="repo1", path="/tmp/repo1", priority=10, active_branch="main"),
            "repo2": RepoConfig(id="repo2", path="/tmp/repo2", priority=5, active_branch="dev")
        }
    )

@patch("prime_directive.bin.pd.load_registry")
def test_list_command(mock_load, mock_registry):
    mock_load.return_value = mock_registry
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "repo1" in result.stdout
    assert "repo2" in result.stdout
    assert "10" in result.stdout  # Priority

@patch("prime_directive.bin.pd.load_registry")
@patch("prime_directive.bin.pd.get_status")
@patch("prime_directive.bin.pd.asyncio.run") # Mocking asyncio.run to avoid actual DB calls in unit test
def test_status_command(mock_async_run, mock_get_status, mock_load, mock_registry):
    mock_load.return_value = mock_registry
    
    # Mock get_status return values
    mock_get_status.return_value = {
        "branch": "main",
        "is_dirty": False,
        "uncommitted_files": [],
        "diff_stat": ""
    }
    
    mock_async_run.return_value = "2025-01-01 12:00"

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Prime Directive Status" in result.stdout
    assert "repo1" in result.stdout
    assert "Clean" in result.stdout
    assert "2025-01-01 12:00" in result.stdout

@patch("prime_directive.bin.pd.load_registry")
@patch("shutil.which")
@patch("requests.get")
@patch("os.path.exists")
def test_doctor_command(mock_exists, mock_get, mock_which, mock_load, mock_registry):
    mock_load.return_value = mock_registry
    
    # Mock shutil.which
    def which_side_effect(cmd):
        if cmd == "tmux": return "/usr/bin/tmux"
        if cmd == "code": return "/usr/bin/code"
        return None
    mock_which.side_effect = which_side_effect
    
    # Mock requests.get (Ollama)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "gpt-4:latest"}]} # Matches mock_registry model
    mock_get.return_value = mock_response
    
    # Mock os.path.exists
    mock_exists.return_value = True

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Prime Directive Doctor" in result.stdout
    assert "Tmux Installed" in result.stdout
    assert "✅" in result.stdout
