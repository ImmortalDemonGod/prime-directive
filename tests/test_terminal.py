import pytest
from unittest.mock import patch

from prime_directive.core.terminal import capture_terminal_state


async def test_capture_terminal_state_tmux_success():
    with patch(
        "prime_directive.core.terminal._run_tmux_command",
        return_value=(0, "Line 1\nLine 2\n...Line 50", ""),
    ) as mock_run:
        last_cmd, output = await capture_terminal_state()

        assert output == "Line 1\nLine 2\n...Line 50"
        assert last_cmd == "unknown"  # Placeholder for now
        mock_run.assert_called_with(
            ["tmux", "capture-pane", "-p", "-S", "-50"],
            timeout_seconds=2,
        )


async def test_capture_terminal_state_tmux_with_repo_id():
    with patch(
        "prime_directive.core.terminal._run_tmux_command",
        return_value=(0, "Session Output", ""),
    ) as mock_run:
        _cmd, output = await capture_terminal_state(repo_id="my-repo")

        assert output == "Session Output"
        mock_run.assert_called_with(
            ["tmux", "capture-pane", "-p", "-S", "-50", "-t", "pd-my-repo"],
            timeout_seconds=2,
        )


async def test_capture_terminal_state_tmux_failure():
    with patch(
        "prime_directive.core.terminal._run_tmux_command",
        return_value=(1, "", "not a terminal"),
    ):
        last_cmd, output = await capture_terminal_state()

        assert output == "No tmux session found or capture failed."
        assert last_cmd == "unknown"


async def test_capture_terminal_state_no_tmux_installed():
    with patch(
        "prime_directive.core.terminal._run_tmux_command",
        side_effect=FileNotFoundError,
    ):
        _cmd, output = await capture_terminal_state()
        assert output == "tmux not installed."
