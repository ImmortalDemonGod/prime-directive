import subprocess
import os
import shutil


def ensure_session(repo_id: str, repo_path: str, attach: bool = True):
    """
    Ensures a tmux session exists for the given repo_id and attaches to it.
    If the session doesn't exist, it creates one starting at repo_path.
    
    Args:
        repo_id (str): The ID of the repository (used for session name).
        repo_path (str): The path to the repository.
    """
    if not shutil.which("tmux"):
        print("Error: tmux is not installed.")
        return

    session_name = f"pd-{repo_id}"

    # Check if session exists
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=2
        )
    except subprocess.TimeoutExpired:
        print(f"Error: tmux has-session timed out for {session_name}")
        return

    if result.returncode != 0:
        # Create new session
        # Use tmux start-directory (-c) to avoid shell interpolation / injection risk.
        try:
            if shutil.which("uv"):
                subprocess.run(
                    [
                        "tmux",
                        "new-session",
                        "-d",
                        "-s",
                        session_name,
                        "-c",
                        repo_path,
                        "uv",
                        "shell",
                    ],
                    timeout=5,
                )
            else:
                shell = os.environ.get("SHELL") or "bash"
                subprocess.run(
                    [
                        "tmux",
                        "new-session",
                        "-d",
                        "-s",
                        session_name,
                        "-c",
                        repo_path,
                        shell,
                    ],
                    timeout=5,
                )
        except subprocess.TimeoutExpired:
            print(f"Error: tmux new-session timed out for {session_name}")
            return

    # Attach logic
    # If we are already inside a tmux session, we must use switch-client
    if os.environ.get("TMUX"):
        try:
            subprocess.run(
                ["tmux", "switch-client", "-t", session_name],
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            print("Error: tmux switch-client timed out")
    else:
        # Otherwise attach normally
        # NOTE: attach-session is interactive and blocks until the user detaches.
        # We do NOT put a timeout here as it would kill the user's session.
        if attach:
            subprocess.run(["tmux", "attach-session", "-t", session_name])


def detach_current():
    """
    Detaches the current tmux client if inside a session.
    """
    if os.environ.get("TMUX"):
        try:
            subprocess.run(["tmux", "detach-client"], timeout=2)
        except subprocess.TimeoutExpired:
            print("Error: tmux detach-client timed out")
