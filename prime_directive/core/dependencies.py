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
    """
    Provide a platform-appropriate installation instruction for Ollama.
    
    Returns:
        str: Installation command or guidance — the Homebrew install command on macOS, a shell curl installer on Linux, or a download URL instruction for other systems.
    """
    system = platform.system()
    if system == "Darwin":
        return "brew install ollama"
    if system == "Linux":
        return "curl -fsSL https://ollama.com/install.sh | sh"
    return "See https://ollama.com/download"


def is_ollama_installed() -> bool:
    """
    Check whether the 'ollama' executable is available on the system PATH.
    
    Returns:
        `true` if the 'ollama' executable is found on PATH, `false` otherwise.
    """
    return shutil.which("ollama") is not None


def check_ollama_running(
    api_tags_url: str = "http://localhost:11434/api/tags",
    timeout_seconds: float = 2.0,
) -> bool:
    """
    Check whether an Ollama server responds at the tags API endpoint.
    
    Parameters:
        api_tags_url (str): Full URL to the Ollama `/api/tags` endpoint to probe.
        timeout_seconds (float): Maximum time in seconds to wait for the HTTP response; if the request times out or fails, the server is considered not running.
    
    Returns:
        `true` if the endpoint returns HTTP status 200, `false` otherwise.
    """
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
    """
    Check whether an Ollama model with the given name is listed by the Ollama API.
    
    Queries the provided tags endpoint and considers a model present when a listed model name equals `model_name` or starts with `model_name:`.
    
    Parameters:
        model_name (str): Model name to search for.
        api_tags_url (str): URL of the Ollama tags endpoint to query.
        timeout_seconds (float): HTTP request timeout in seconds.
    
    Returns:
        True if a matching model is present, False otherwise.
    """
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
    """
    Assess Ollama installation, runtime status, and whether a specific model is available, and return a consolidated DependencyStatus.
    
    Parameters:
        model_name (str): Exact or prefix name of the Ollama model to check for presence.
        api_base (str): Base URL of the Ollama API (e.g., "http://localhost:11434").
    
    Returns:
        DependencyStatus: An immutable status object indicating:
            - whether Ollama is installed,
            - whether the Ollama daemon is running,
            - whether the requested model is present,
            - a human-readable details message,
            - optional actionable commands for install, start, and check operations.
    """
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
    """
    Check whether an OpenAI API key is set in the environment.
    
    Parameters:
        env_var (str): Environment variable name to check. Defaults to "OPENAI_API_KEY".
    
    Returns:
        `true` if the environment variable exists and is non-empty, `false` otherwise.
    """
    value = os.getenv(env_var)
    return bool(value)