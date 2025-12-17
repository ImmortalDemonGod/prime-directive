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
    """Check if running inside a virtual environment."""
    return sys.prefix != sys.base_prefix

def ensure_packages(packages: List[str], auto_install: bool = False) -> None:
    """
    Ensure the specified Python packages are installed.
    
    If auto_install is True and we are in a venv, attempts to install
    missing packages that are on the ALLOWLIST.
    
    Args:
        packages: List of package names to check/install.
        auto_install: Whether to attempt installation if missing.
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
