import pytest
from unittest.mock import patch, MagicMock
from prime_directive.core.terminal import capture_terminal_state

def test_capture_terminal_state_tmux_success():
    with patch("subprocess.run") as mock_run:
        # Mock successful tmux capture
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Line 1\nLine 2\n...Line 50"
        )
        
        last_cmd, output = capture_terminal_state()
        
        assert output == "Line 1\nLine 2\n...Line 50"
        assert last_cmd == "unknown"  # Placeholder for now
        mock_run.assert_called_with(
            ["tmux", "capture-pane", "-p", "-S", "-50"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2
        )

def test_capture_terminal_state_tmux_with_repo_id():
    with patch("subprocess.run") as mock_run:
        # Mock successful tmux capture
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Session Output"
        )
        
        _cmd, output = capture_terminal_state(repo_id="my-repo")
        
        assert output == "Session Output"
        mock_run.assert_called_with(
            ["tmux", "capture-pane", "-p", "-S", "-50", "-t", "pd-my-repo"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2
        )

def test_capture_terminal_state_tmux_failure():
    with patch("subprocess.run") as mock_run:
        # Mock failed tmux capture (e.g. not in tmux)
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="not a terminal"
        )
        
        last_cmd, output = capture_terminal_state()
        
        assert output == "No tmux session found or capture failed."
        assert last_cmd == "unknown"

def test_capture_terminal_state_no_tmux_installed():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        _cmd, output = capture_terminal_state()
        assert output == "tmux not installed."
