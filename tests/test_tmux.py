import pytest
import os
from unittest.mock import patch, MagicMock, call
from prime_directive.core.tmux import ensure_session, detach_current

@patch("shutil.which")
@patch("subprocess.run")
@patch.dict(os.environ, {}, clear=True)
def test_ensure_session_create_new_outside_tmux(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/tmux"
    # Mock has-session failure (session doesn't exist)
    mock_run.side_effect = [
        MagicMock(returncode=1), # has-session
        MagicMock(returncode=0), # new-session
        MagicMock(returncode=0)  # attach-session
    ]
    
    ensure_session("test-repo", "/path/to/repo")
    
    assert mock_run.call_count == 3
    # Check new-session call
    new_session_call = mock_run.call_args_list[1]
    assert new_session_call[0][0][:4] == ["tmux", "new-session", "-d", "-s"]
    assert new_session_call[0][0][4] == "pd-test-repo"
    # Check attach call
    attach_call = mock_run.call_args_list[2]
    assert attach_call[0][0] == ["tmux", "attach-session", "-t", "pd-test-repo"]

@patch("shutil.which")
@patch("subprocess.run")
@patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,123,0"}, clear=True)
def test_ensure_session_exists_inside_tmux(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/tmux"
    # Mock has-session success (session exists)
    mock_run.side_effect = [
        MagicMock(returncode=0), # has-session
        MagicMock(returncode=0)  # switch-client
    ]
    
    ensure_session("test-repo", "/path/to/repo")
    
    assert mock_run.call_count == 2
    # Check switch-client call (since TMUX env var is set)
    switch_call = mock_run.call_args_list[1]
    assert switch_call[0][0] == ["tmux", "switch-client", "-t", "pd-test-repo"]

@patch("shutil.which")
@patch("subprocess.run")
@patch.dict(os.environ, {"TMUX": "something"}, clear=True)
def test_detach_current(mock_run, mock_which):
    detach_current()
    mock_run.assert_called_once_with(["tmux", "detach-client"])

@patch("shutil.which")
@patch("subprocess.run")
@patch.dict(os.environ, {}, clear=True)
def test_detach_current_no_tmux(mock_run, mock_which):
    detach_current()
    mock_run.assert_not_called()
