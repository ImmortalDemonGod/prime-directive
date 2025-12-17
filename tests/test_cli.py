import pytest
from typer.testing import CliRunner
from unittest.mock import patch, Mock, MagicMock, AsyncMock
from prime_directive.bin.pd import app
from omegaconf import OmegaConf
from datetime import datetime, timezone

from prime_directive.core.db import EventLog, EventType

runner = CliRunner()


@pytest.fixture
def mock_config(tmp_path):
    # Use OmegaConf to create a DictConfig that supports dot access
    log_file = tmp_path / "pd.log"
    conf_dict = {
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
            "repo1": {
                "id": "repo1",
                "path": "/tmp/repo1",
                "priority": 10,
                "active_branch": "main",
            },
            "repo2": {
                "id": "repo2",
                "path": "/tmp/repo2",
                "priority": 5,
                "active_branch": "dev",
            },
        },
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
@patch("prime_directive.bin.pd.get_status", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_session")
@patch("prime_directive.bin.pd.dispose_engine", new_callable=AsyncMock)
def test_status_command(
    mock_dispose,
    mock_get_session,
    mock_init_db,
    mock_get_status,
    mock_load,
    mock_config,
):
    mock_load.return_value = mock_config

    # Mock get_status return values
    mock_get_status.return_value = {
        "branch": "main",
        "is_dirty": False,
        "uncommitted_files": [],
        "diff_stat": "",
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
    mock_init_db.assert_awaited_once()


@patch("prime_directive.bin.pd.load_config")
@patch("shutil.which")
@patch("requests.get")
@patch("os.path.exists")
def test_doctor_command(
    mock_exists, mock_get, mock_which, mock_load, mock_config
):
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
    mock_response.json.return_value = {
        "models": [{"name": "gpt-4:latest"}]
    }  # Matches mock_config model
    mock_get.return_value = mock_response

    # Mock os.path.exists
    mock_exists.return_value = True

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Prime Directive Doctor" in result.stdout
    assert "Tmux Installed" in result.stdout
    assert "✅" in result.stdout


@patch("prime_directive.bin.pd.load_config")
@patch("shutil.which")
@patch("requests.get")
@patch("os.path.exists")
def test_doctor_detects_multiple_installations(
    mock_exists, mock_get, mock_which, mock_load, mock_config, tmp_path
):
    """Test that doctor warns about multiple pd installations that can cause config shadowing."""
    mock_load.return_value = mock_config

    def which_side_effect(cmd):
        if cmd == "tmux":
            return "/usr/bin/tmux"
        if cmd == "code":
            return "/usr/bin/code"
        return None

    mock_which.side_effect = which_side_effect

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "gpt-4:latest"}]}
    mock_get.return_value = mock_response

    mock_exists.return_value = True

    # Patch Path.home() to use tmp_path and create a fake UV installation
    uv_tools_dir = tmp_path / ".local" / "share" / "uv" / "tools" / "prime-directive"
    uv_tools_dir.mkdir(parents=True)

    with patch("prime_directive.bin.pd.Path.home", return_value=tmp_path):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Installation" in result.stdout
    assert "⚠️" in result.stdout or "Multiple installs" in result.stdout


@patch("prime_directive.bin.pd.load_config")
def test_install_hooks_creates_post_commit(mock_load, tmp_path, mock_config):
    repo_path = tmp_path / "repo1"
    hooks_dir = repo_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)

    conf_dict = OmegaConf.to_container(mock_config, resolve=True)
    conf_dict["repos"]["repo1"]["path"] = str(repo_path)
    cfg = OmegaConf.create(conf_dict)
    mock_load.return_value = cfg

    result = runner.invoke(app, ["install-hooks", "repo1"])
    assert result.exit_code == 0

    hook_path = hooks_dir / "post-commit"
    assert hook_path.exists()
    content = hook_path.read_text(encoding="utf-8")
    assert "_internal-log-commit repo1" in content


@patch("prime_directive.bin.pd.load_config")
def test_install_hooks_missing_git_dir_exits_1(
    mock_load,
    tmp_path,
    mock_config,
):
    repo_path = tmp_path / "repo1"
    repo_path.mkdir(parents=True)

    conf_dict = OmegaConf.to_container(mock_config, resolve=True)
    conf_dict["repos"]["repo1"]["path"] = str(repo_path)
    cfg = OmegaConf.create(conf_dict)
    mock_load.return_value = cfg

    result = runner.invoke(app, ["install-hooks", "repo1"])
    assert result.exit_code == 1
    assert "missing .git" in result.stdout


@patch("prime_directive.bin.pd.load_config")
def test_install_hooks_permission_denied_exits_1(
    mock_load,
    tmp_path,
    mock_config,
    monkeypatch,
):
    repo_path = tmp_path / "repo1"
    hooks_dir = repo_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)

    conf_dict = OmegaConf.to_container(mock_config, resolve=True)
    conf_dict["repos"]["repo1"]["path"] = str(repo_path)
    cfg = OmegaConf.create(conf_dict)
    mock_load.return_value = cfg

    import builtins

    real_open = builtins.open

    def open_side_effect(path, *args, **kwargs):
        """
        Simulate opening a file but raise PermissionError when the target path ends with "post-commit".
        
        Parameters:
            path: The file path to open; may be a str or path-like object. If the string form of `path` ends with "post-commit", this function raises PermissionError.
        
        Returns:
            The file object returned by the underlying `real_open` call for the given path and mode.
        """
        if str(path).endswith("post-commit"):
            raise PermissionError
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", open_side_effect)

    result = runner.invoke(app, ["install-hooks", "repo1"])
    assert result.exit_code == 1
    assert "failed to install post-commit hook" in result.stdout


@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_session")
@patch("prime_directive.bin.pd.dispose_engine", new_callable=AsyncMock)
def test_internal_log_commit_writes_event(
    _mock_dispose,
    mock_get_session,
    _mock_init_db,
    mock_load,
    mock_config,
):
    mock_load.return_value = mock_config

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def async_gen(_db_path=None):
        """
        Provide an asynchronous generator that yields the current database session.
        
        Parameters:
            _db_path (str | None): Optional database path placeholder (unused by this generator).
        
        Returns:
            session: An active asynchronous database session to be used as an async context manager or awaited consumer.
        """
        yield session

    mock_get_session.side_effect = async_gen

    result = runner.invoke(app, ["_internal-log-commit", "repo1"])
    assert result.exit_code == 0

    added = session.add.call_args[0][0]
    assert isinstance(added, EventLog)
    assert added.repo_id == "repo1"
    assert added.event_type == EventType.COMMIT


@patch("prime_directive.bin.pd.load_config")
@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
@patch("prime_directive.bin.pd.get_session")
@patch("prime_directive.bin.pd.dispose_engine", new_callable=AsyncMock)
def test_metrics_reports_ttc(
    _mock_dispose,
    mock_get_session,
    _mock_init_db,
    mock_load,
    mock_config,
):
    """
    Verify the CLI 'metrics' command reports time-to-change metrics for a repository when SWITCH_IN and COMMIT events are present.
    
    Invokes the CLI with a mocked database session that returns two EventLog entries one minute apart and asserts the output contains the metrics header and the repository identifier.
    """
    mock_load.return_value = mock_config

    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    events = [
        EventLog(
            repo_id="repo1", event_type=EventType.SWITCH_IN, timestamp=t0
        ),
        EventLog(
            repo_id="repo1",
            event_type=EventType.COMMIT,
            timestamp=t0.replace(minute=t0.minute + 1),
        ),
    ]

    session = MagicMock()
    result_obj = MagicMock()
    result_obj.scalars.return_value.all.return_value = events
    session.execute = AsyncMock(return_value=result_obj)

    async def async_gen(_db_path=None):
        """
        Provide an asynchronous generator that yields the current database session.
        
        Parameters:
            _db_path (str | None): Optional database path placeholder (unused by this generator).
        
        Returns:
            session: An active asynchronous database session to be used as an async context manager or awaited consumer.
        """
        yield session

    mock_get_session.side_effect = async_gen

    result = runner.invoke(app, ["metrics", "--repo", "repo1"])
    assert result.exit_code == 0
    assert "Prime Directive Metrics" in result.stdout
    assert "repo1" in result.stdout