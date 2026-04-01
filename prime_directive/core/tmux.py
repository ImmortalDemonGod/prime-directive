import asyncio
import logging
import os
import shutil

logger = logging.getLogger("prime_directive")


async def ensure_session(repo_id: str, repo_path: str, attach: bool = True) -> None:
    """Ensure a tmux session exists for the given repo_id and attach/switch to it.

    Uses asyncio.create_subprocess_exec throughout to avoid blocking the event loop.
    """
    if not shutil.which("tmux"):
        logger.error("tmux is not installed")
        return

    session_name = f"pd-{repo_id}"

    # Check if session exists
    try:
        proc = await asyncio.create_subprocess_exec(
            "tmux", "has-session", "-t", session_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        returncode = await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.error("tmux has-session timed out for %s", session_name)
        return

    if returncode != 0:
        # Create new session
        if shutil.which("uv"):
            cmd = ["tmux", "new-session", "-d", "-s", session_name, "-c", repo_path, "uv", "shell"]
        else:
            shell = os.environ.get("SHELL") or "bash"
            cmd = ["tmux", "new-session", "-d", "-s", session_name, "-c", repo_path, shell]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("tmux new-session timed out for %s", session_name)
            return

    # Attach logic
    if os.environ.get("TMUX"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "switch-client", "-t", session_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.error("tmux switch-client timed out")
    elif attach:
        # attach-session is interactive and blocks until the user detaches —
        # run it without a timeout via a standard subprocess to preserve interactivity.
        import subprocess
        subprocess.run(["tmux", "attach-session", "-t", session_name])


async def detach_current() -> None:
    """Detach the current tmux client if inside a session."""
    if os.environ.get("TMUX"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "detach-client",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.error("tmux detach-client timed out")
