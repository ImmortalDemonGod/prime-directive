import sys
from unittest.mock import patch, MagicMock, call
import pytest
from prime_directive.core.auto_installer import ensure_packages, is_venv

@pytest.fixture
def mock_importlib():
    with patch("prime_directive.core.auto_installer.importlib.util.find_spec") as mock:
        yield mock

@pytest.fixture
def mock_subprocess():
    with patch("prime_directive.core.auto_installer.subprocess.check_call") as mock:
        yield mock

@pytest.fixture
def mock_sys_prefix():
    with patch("prime_directive.core.auto_installer.sys") as mock_sys:
        # Default: simulated venv (prefix != base_prefix)
        mock_sys.prefix = "/some/venv"
        mock_sys.base_prefix = "/usr/local"
        mock_sys.executable = "/some/venv/bin/python"
        yield mock_sys

def test_is_venv_true(mock_sys_prefix):
    assert is_venv() is True

def test_is_venv_false():
    with patch("prime_directive.core.auto_installer.sys") as mock_sys:
        mock_sys.prefix = "/usr/local"
        mock_sys.base_prefix = "/usr/local"
        assert is_venv() is False

def test_ensure_packages_no_missing(mock_importlib, mock_subprocess):
    # Setup: package exists
    mock_importlib.return_value = True
    
    ensure_packages(["openai"], auto_install=True)
    
    # Should check import but not install
    mock_importlib.assert_called_with("openai")
    mock_subprocess.assert_not_called()

def test_ensure_packages_missing_no_auto_install(mock_importlib, mock_subprocess, mock_sys_prefix):
    # Setup: package missing
    mock_importlib.return_value = None
    
    ensure_packages(["openai"], auto_install=False)
    
    mock_subprocess.assert_not_called()

def test_ensure_packages_missing_auto_install_success(mock_importlib, mock_subprocess, mock_sys_prefix):
    # Setup: package missing, in venv, allowlisted
    mock_importlib.return_value = None
    
    ensure_packages(["openai"], auto_install=True)
    
    mock_subprocess.assert_called_once_with(
        ["/some/venv/bin/python", "-m", "pip", "install", "openai"]
    )

def test_ensure_packages_not_allowlisted(mock_importlib, mock_subprocess, mock_sys_prefix):
    # Setup: malicious/unknown package
    mock_importlib.return_value = None
    
    ensure_packages(["evil-package"], auto_install=True)
    
    # Should check import but NOT install
    mock_subprocess.assert_not_called()

def test_ensure_packages_not_in_venv(mock_importlib, mock_subprocess):
    # Setup: package missing, auto_install=True, BUT not in venv
    mock_importlib.return_value = None
    
    with patch("prime_directive.core.auto_installer.sys") as mock_sys:
        mock_sys.prefix = "/usr/local"
        mock_sys.base_prefix = "/usr/local"
        
        ensure_packages(["openai"], auto_install=True)
    
    mock_subprocess.assert_not_called()
