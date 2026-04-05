import asyncio
import logging
import os
import shutil

logger = logging.getLogger("prime_directive")


async def ensure_session(
    repo_id: str, repo_path: str, attach: bool = True
) -> bool:
    """
    Ensure a tmux session named "pd-<repo_id>" exists and, if requested, attach or switch the client to it.

    Creates a detached session in the given repository path using the user's shell when the session is missing. If the process is already inside a tmux client, attempts to switch the client to that session; otherwise, when `attach` is True, runs an interactive attach to that session.

    Parameters:
        repo_id (str): Identifier used to form the session name as "pd-<repo_id>".
        repo_path (str): Directory to use as the session's working directory when creating a new session.
        attach (bool): If True and not already inside tmux, perform an interactive attach to the session.

    Returns:
        bool: `True` if the session exists or was successfully created and the attach/switch was attempted, `False` on failure.
    """
    if not shutil.which("tmux"):
        logger.error("tmux is not installed")
        return False

    session_name = f"pd-{repo_id}"

    # Check if session exists
    try:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "has-session",
            "-t",
            session_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        returncode = await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.error("tmux has-session timed out for %s", session_name)
        return False

    if returncode != 0:
        # Create new session in the repo directory using the user's shell
        shell = os.environ.get("SHELL") or "bash"
        cmd = [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session_name,
            "-c",
            repo_path,
            shell,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            rc = await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("tmux new-session timed out for %s", session_name)
            return False
        if rc != 0:
            logger.error(
                "tmux new-session failed for %s (exit %d)",
                session_name,
                rc,
            )
            return False

    # Attach logic
    if os.environ.get("TMUX"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "switch-client",
                "-t",
                session_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.error("tmux switch-client timed out")
            return False
    elif attach:
        # attach-session is interactive and blocks until the user detaches —
        # run it without a timeout via a standard subprocess to preserve interactivity.
        import subprocess

        subprocess.run(["tmux", "attach-session", "-t", session_name])

    return True


async def detach_current() -> None:
    """Detach the current tmux client if inside a session."""
    if os.environ.get("TMUX"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "detach-client",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.error("tmux detach-client timed out")
