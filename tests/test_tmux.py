import os
from unittest.mock import AsyncMock, MagicMock, patch

from prime_directive.core.tmux import detach_current, ensure_session


def _make_proc(returncode: int) -> AsyncMock:
    """
    Create an AsyncMock that simulates a subprocess whose `wait()` coroutine returns the given exit code.
    
    Parameters:
        returncode (int): Exit code that the mock process's `wait()` coroutine will return.
    
    Returns:
        AsyncMock: A mock process object with `wait()` set to return `returncode`.
    """
    proc = AsyncMock()
    proc.wait = AsyncMock(return_value=returncode)
    return proc


def _which_tmux_only(name: str) -> str | None:
    """
    Provide a which-like lookup that yields a tmux executable path only for the name "tmux".
    
    Parameters:
        name (str): The program name to query.
    
    Returns:
        str | None: "/usr/bin/tmux" if `name` is "tmux", `None` otherwise.
    """
    return "/usr/bin/tmux" if name == "tmux" else None


@patch("shutil.which", side_effect=_which_tmux_only)
@patch("asyncio.create_subprocess_exec")
@patch("subprocess.run")
@patch.dict(os.environ, {}, clear=True)
async def test_ensure_session_create_new_outside_tmux(
    mock_run, mock_cse, mock_which
):
    # has-session → fail, new-session → ok; attach is synchronous subprocess.run
    mock_cse.side_effect = [
        _make_proc(1),  # has-session
        _make_proc(0),  # new-session
    ]
    mock_run.return_value = MagicMock(returncode=0)  # attach-session

    result = await ensure_session("test-repo", "/path/to/repo")

    assert result is True
    assert mock_cse.call_count == 2
    has_session_args = mock_cse.call_args_list[0][0]
    assert list(has_session_args[:3]) == ["tmux", "has-session", "-t"]

    new_session_args = mock_cse.call_args_list[1][0]
    assert list(new_session_args[:4]) == [
        "tmux",
        "new-session",
        "-d",
        "-s",
    ]
    assert new_session_args[4] == "pd-test-repo"
    # new-session should NOT contain "uv" anywhere
    assert "uv" not in new_session_args

    # attach-session falls through to blocking subprocess.run
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == [
        "tmux",
        "attach-session",
        "-t",
        "pd-test-repo",
    ]


@patch("shutil.which", side_effect=_which_tmux_only)
@patch("asyncio.create_subprocess_exec")
@patch.dict(
    os.environ,
    {"TMUX": "/tmp/tmux-1000/default,123,0"},
    clear=True,
)
async def test_ensure_session_exists_inside_tmux(mock_cse, mock_which):
    # has-session → ok, switch-client → ok
    mock_cse.side_effect = [
        _make_proc(0),  # has-session
        _make_proc(0),  # switch-client
    ]

    result = await ensure_session("test-repo", "/path/to/repo")

    assert result is True
    assert mock_cse.call_count == 2
    switch_args = mock_cse.call_args_list[1][0]
    assert list(switch_args[:4]) == [
        "tmux",
        "switch-client",
        "-t",
        "pd-test-repo",
    ]


@patch("shutil.which", side_effect=_which_tmux_only)
@patch("asyncio.create_subprocess_exec")
@patch.dict(os.environ, {}, clear=True)
async def test_ensure_session_new_session_failure_returns_false(
    mock_cse, mock_which
):
    """When tmux new-session fails, ensure_session returns False."""
    mock_cse.side_effect = [
        _make_proc(1),  # has-session → not found
        _make_proc(1),  # new-session → fails
    ]

    result = await ensure_session("bad-repo", "/nonexistent")

    assert result is False
    assert mock_cse.call_count == 2


@patch("shutil.which", return_value=None)
@patch.dict(os.environ, {}, clear=True)
async def test_ensure_session_no_tmux_installed(mock_which):
    """When tmux is not installed, ensure_session returns False."""
    result = await ensure_session("repo", "/path")
    assert result is False


@patch("asyncio.create_subprocess_exec")
@patch.dict(os.environ, {"TMUX": "something"}, clear=True)
async def test_detach_current(mock_cse):
    mock_cse.return_value = _make_proc(0)

    await detach_current()

    mock_cse.assert_called_once()
    assert mock_cse.call_args[0][:2] == ("tmux", "detach-client")


@patch("asyncio.create_subprocess_exec")
@patch.dict(os.environ, {}, clear=True)
async def test_detach_current_no_tmux(mock_cse):
    await detach_current()
    mock_cse.assert_not_called()
