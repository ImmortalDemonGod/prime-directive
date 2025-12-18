import logging
import subprocess
import sys
import importlib.util
from typing import List

logger = logging.getLogger(__name__)

# Strict allowlist of packages we are willing to auto-install
# This prevents arbitrary code execution or bloating the venv with unexpected deps.
ALLOWLIST = {
    "openai",
    "tenacity",
    "tiktoken",
    "requests",
    "httpx",
}

def is_venv() -> bool:
    """
    Determine whether the current Python interpreter is running inside a virtual environment.
    
    Returns:
        bool: `True` if running in a virtual environment, `False` otherwise.
    """
    return sys.prefix != sys.base_prefix

def ensure_packages(packages: List[str], auto_install: bool = False) -> None:
    """
    Ensure the listed Python packages are available, optionally installing missing allowlisted packages when running inside a virtual environment.
    
    If any packages are missing and `auto_install` is False, the function logs a warning and returns. If `auto_install` is True but the interpreter is not in a virtual environment, the function logs an error and returns. When `auto_install` is True and running in a virtual environment, only packages present in `ALLOWLIST` will be installed; non-allowlisted packages are skipped with a warning. The function attempts installation via pip and logs success or failure.
    
    Parameters:
        packages (List[str]): Package names to check for importability.
        auto_install (bool): If True, attempt to install missing packages from `ALLOWLIST` when in a virtual environment.
    """
    missing = []
    for pkg in packages:
        if not importlib.util.find_spec(pkg):
            missing.append(pkg)
    
    if not missing:
        return

    if not auto_install:
        logger.warning(
            f"Missing optional packages: {', '.join(missing)}. "
            "Set system.auto_install_python_deps=true to install automatically."
        )
        return

    if not is_venv():
        logger.error(
            "Cannot auto-install dependencies: Not running in a virtual environment. "
            f"Missing: {', '.join(missing)}"
        )
        return

    # Filter by allowlist
    to_install = [p for p in missing if p in ALLOWLIST]
    skipped = [p for p in missing if p not in ALLOWLIST]

    if skipped:
        logger.warning(
            f"Skipping auto-install for non-allowlisted packages: {', '.join(skipped)}"
        )

    if not to_install:
        return

    logger.info(f"Auto-installing missing packages: {', '.join(to_install)}...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + to_install
        )
        logger.info("Successfully installed packages.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to auto-install packages: {e}")