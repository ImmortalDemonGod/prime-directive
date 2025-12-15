from dataclasses import dataclass
from typing import Optional
import os
import platform
import shutil

import requests


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    installed: bool
    running: bool
    details: str
    install_cmd: Optional[str] = None
    start_cmd: Optional[str] = None
    check_cmd: Optional[str] = None


def get_ollama_install_cmd() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install ollama"
    if system == "Linux":
        return "curl -fsSL https://ollama.com/install.sh | sh"
    return "See https://ollama.com/download"


def is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def check_ollama_running(
    api_tags_url: str = "http://localhost:11434/api/tags",
    timeout_seconds: float = 2.0,
) -> bool:
    try:
        resp = requests.get(api_tags_url, timeout=timeout_seconds)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def check_ollama_model_present(
    model_name: str,
    api_tags_url: str = "http://localhost:11434/api/tags",
    timeout_seconds: float = 2.0,
) -> bool:
    try:
        resp = requests.get(api_tags_url, timeout=timeout_seconds)
        if resp.status_code != 200:
            return False
        models = resp.json().get("models", [])
        model_names = [
            m.get("name", "") for m in models if isinstance(m, dict)
        ]
        return any(
            name == model_name or name.startswith(f"{model_name}:")
            for name in model_names
        )
    except requests.exceptions.RequestException:
        return False
    except (ValueError, KeyError):
        return False


def get_ollama_status(
    model_name: str,
    api_base: str = "http://localhost:11434",
) -> DependencyStatus:
    tags_url = f"{api_base}/api/tags"
    installed = is_ollama_installed()
    running = False

    if installed:
        running = check_ollama_running(tags_url)

    install_cmd = get_ollama_install_cmd()
    start_cmd = "ollama serve &"
    check_cmd = f"curl {tags_url}"

    if not installed:
        return DependencyStatus(
            name="Ollama",
            installed=False,
            running=False,
            details="Not installed",
            install_cmd=install_cmd,
            start_cmd=start_cmd,
            check_cmd=check_cmd,
        )

    if not running:
        return DependencyStatus(
            name="Ollama",
            installed=True,
            running=False,
            details="Installed but not running (localhost:11434)",
            install_cmd=install_cmd,
            start_cmd=start_cmd,
            check_cmd=check_cmd,
        )

    if not check_ollama_model_present(model_name, tags_url):
        return DependencyStatus(
            name="Ollama",
            installed=True,
            running=True,
            details=(
                f"Running but model '{model_name}' missing "
                f"(run: ollama pull {model_name})"
            ),
            install_cmd=install_cmd,
            start_cmd=start_cmd,
            check_cmd=check_cmd,
        )

    return DependencyStatus(
        name="Ollama",
        installed=True,
        running=True,
        details=f"Running and model '{model_name}' found",
        install_cmd=install_cmd,
        start_cmd=start_cmd,
        check_cmd=check_cmd,
    )


def has_openai_api_key(env_var: str = "OPENAI_API_KEY") -> bool:
    value = os.getenv(env_var)
    return bool(value)
