import subprocess
import os
import shutil

def ensure_session(repo_id: str, repo_path: str):
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
        # We use a shell command to change dir and start shell
        # Note: 'uv shell' might fail if not in a project with .venv, fall back to $SHELL
        # Using bash -c as per PRD suggestion, but making it more robust
        cmd = f"cd {repo_path} && (uv shell || $SHELL)"
        try:
            subprocess.run([
                "tmux", "new-session", "-d", "-s", session_name,
                "bash", "-c", cmd
            ], timeout=5)
        except subprocess.TimeoutExpired:
            print(f"Error: tmux new-session timed out for {session_name}")
            return
    
    # Attach logic
    # If we are already inside a tmux session, we must use switch-client
    if os.environ.get("TMUX"):
        try:
            subprocess.run(["tmux", "switch-client", "-t", session_name], timeout=2)
        except subprocess.TimeoutExpired:
            print("Error: tmux switch-client timed out")
    else:
        # Otherwise attach normally
        # NOTE: attach-session is interactive and blocks until the user detaches.
        # We do NOT put a timeout here as it would kill the user's session.
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
