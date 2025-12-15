import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock, call
from prime_directive.bin.pd import app
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
            "db_path": ":memory:",
            "log_path": str(log_file),
            "mock_mode": False
        },
        "repos": {
            "current-repo": {"id": "current-repo", "path": "/tmp/current-repo", "priority": 10},
            "target-repo": {"id": "target-repo", "path": "/tmp/target-repo", "priority": 8}
        }
    })

@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.os.getcwd")
@patch("prime_directive.bin.pd.freeze_logic", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.ensure_session")
@patch("prime_directive.bin.pd.launch_editor")
@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_session")
def test_switch_command(mock_get_session, mock_init_db, mock_launch, mock_ensure, mock_freeze, mock_getcwd, mock_load, mock_config):
    mock_load.return_value = mock_config
    mock_getcwd.return_value = "/tmp/current-repo/subdir"
    
    # Mock DB for SITREP retrieval
    mock_session = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.ai_sitrep = "SITREP: Ready for work."
    mock_snapshot.git_status_summary = "Clean"
    # Mock executing the select query
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_snapshot
    mock_session.execute.return_value = mock_result
    
    async def async_gen(*args, **kwargs):
        yield mock_session
    mock_get_session.side_effect = async_gen

    result = runner.invoke(app, ["switch", "target-repo"])
    
    assert result.exit_code == 0
    
    # 1. Verify Freeze of current repo
    mock_freeze.assert_called_once_with("current-repo", mock_config)
    
    # 2. Verify Session & Editor
    assert mock_ensure.call_args_list == [
        call("target-repo", "/tmp/target-repo", attach=False),
        call("target-repo", "/tmp/target-repo"),
    ]
    mock_launch.assert_called_once_with("/tmp/target-repo", "code")
    
    # 3. Verify Output
    assert "WARPING TO TARGET-REPO" in result.stdout
    assert "LAST ACTION: SITREP: Ready for work." in result.stdout

@patch("prime_directive.bin.pd.load_config")
def test_switch_invalid_repo(mock_load, mock_config):
    mock_load.return_value = mock_config
    result = runner.invoke(app, ["switch", "invalid-repo"])
    assert result.exit_code == 1
    assert "Repository 'invalid-repo' not found" in result.stdout
