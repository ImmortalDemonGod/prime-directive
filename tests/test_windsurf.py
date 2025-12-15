import pytest
from unittest.mock import patch
from prime_directive.core.windsurf import launch_editor

@patch("shutil.which")
@patch("subprocess.Popen")
def test_launch_editor_success(mock_popen, mock_which):
    mock_which.return_value = "/usr/bin/windsurf"
    
    launch_editor("/path/to/repo", "windsurf")
    
    mock_popen.assert_called_once_with(["windsurf", "-n", "/path/to/repo"])

@patch("shutil.which")
@patch("subprocess.Popen")
def test_launch_editor_custom_cmd(mock_popen, mock_which):
    mock_which.return_value = "/usr/bin/code"
    
    launch_editor("/path/to/repo", "code")
    
    mock_popen.assert_called_once_with(["code", "-n", "/path/to/repo"])

@patch("shutil.which")
@patch("subprocess.Popen")
def test_launch_editor_not_found(mock_popen, mock_which):
    mock_which.return_value = None
    
    # Should print warning but still try to launch (or handle gracefully)
    # Our implementation tries to launch.
    launch_editor("/path/to/repo", "unknown_editor")
    
    mock_popen.assert_called_once_with(["unknown_editor", "-n", "/path/to/repo"])

@patch("shutil.which")
@patch("subprocess.Popen")
def test_launch_editor_execution_error(mock_popen, mock_which):
    mock_which.return_value = "/usr/bin/windsurf"
    mock_popen.side_effect = FileNotFoundError
    
    # Should catch exception and not crash
    launch_editor("/path/to/repo", "windsurf")
    
    mock_popen.assert_called_once()
