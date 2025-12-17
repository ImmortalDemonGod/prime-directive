import subprocess
import os
import shutil


def ensure_session(repo_id: str, repo_path: str, attach: bool = True):
    """
    Ensure a tmux session named "pd-{repo_id}" exists and switch or attach the client to it.
    
    Creates the session if it does not exist, starting in repo_path. If tmux is not available or tmux commands time out, the function prints an error message and returns without raising. When inside an existing tmux client, the function switches the client to the target session; when not inside tmux and attach is True, it attaches interactively to the session.
    
    Parameters:
        repo_id (str): Identifier used to form the tmux session name as "pd-{repo_id}".
        repo_path (str): Filesystem path used as the session's start directory.
        attach (bool): If True and not already in tmux, attach to the created or existing session; if False, do not attach.
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
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        print(f"Error: tmux has-session timed out for {session_name}")
        return

    if result.returncode != 0:
        # Create new session
        # Use tmux start-directory (-c) to avoid shell interpolation
        # / injection risk.
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
        # NOTE: attach-session is interactive and blocks until the user
        # detaches.
        # We do NOT put a timeout here as it would kill the user's session.
        if attach:
            subprocess.run(["tmux", "attach-session", "-t", session_name])


def detach_current():
    """
    Detach the current tmux client when running inside a tmux session.
    
    If the TMUX environment variable is not set, the function does nothing. If the detach command times out, an error message is printed.
    """
    if os.environ.get("TMUX"):
        try:
            subprocess.run(["tmux", "detach-client"], timeout=2)
        except subprocess.TimeoutExpired:
            print("Error: tmux detach-client timed out")