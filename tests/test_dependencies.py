from unittest.mock import patch, Mock

import requests

from prime_directive.core.dependencies import (
    get_ollama_install_cmd,
    get_ollama_status,
    has_openai_api_key,
)


def test_get_ollama_install_cmd_macos():
    with patch("platform.system", return_value="Darwin"):
        assert get_ollama_install_cmd() == "brew install ollama"


def test_get_ollama_install_cmd_linux():
    with patch("platform.system", return_value="Linux"):
        assert (
            get_ollama_install_cmd()
            == "curl -fsSL https://ollama.com/install.sh | sh"
        )


def test_get_ollama_status_not_installed():
    with patch("shutil.which", return_value=None):
        status = get_ollama_status("qwen2.5-coder")
        assert status.installed is False
        assert status.running is False
        assert "Not installed" in status.details
        assert status.install_cmd
        assert status.start_cmd


def test_get_ollama_status_installed_not_running():
    with (
        patch("shutil.which", return_value="/usr/bin/ollama"),
        patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ),
    ):
        status = get_ollama_status("qwen2.5-coder")
        assert status.installed is True
        assert status.running is False
        assert "not running" in status.details.lower()


def test_get_ollama_status_running_model_missing():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "other-model:latest"}]}

    with (
        patch("shutil.which", return_value="/usr/bin/ollama"),
        patch("requests.get", return_value=mock_resp),
    ):
        status = get_ollama_status("qwen2.5-coder")
        assert status.installed is True
        assert status.running is True
        assert "missing" in status.details.lower()


def test_get_ollama_status_running_model_present():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5-coder:latest"}]
    }

    with (
        patch("shutil.which", return_value="/usr/bin/ollama"),
        patch("requests.get", return_value=mock_resp),
    ):
        status = get_ollama_status("qwen2.5-coder")
        assert status.installed is True
        assert status.running is True
        assert "found" in status.details.lower()


def test_has_openai_api_key_true():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
        assert has_openai_api_key() is True


def test_has_openai_api_key_false():
    with patch.dict("os.environ", {}, clear=True):
        assert has_openai_api_key() is False
