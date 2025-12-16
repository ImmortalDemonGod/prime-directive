import subprocess
import shutil
from typing import Optional


def launch_editor(
    repo_path: str,
    editor_cmd: str = "windsurf",
    editor_args: Optional[list[str]] = None,
):
    """
    Launches the specified editor for the given repository path.

    Args:
        repo_path (str): The path to the repository to open.
        editor_cmd (str): The command to launch the editor (default:
            "windsurf").
    """
    # Verify editor command exists
    if not shutil.which(editor_cmd):
        print(f"Error: Editor command '{editor_cmd}' not found in PATH.")
        return

    try:
        if editor_args is None:
            editor_args = ["-n"]
        subprocess.Popen([editor_cmd, *editor_args, repo_path])
    except FileNotFoundError:
        print(f"Error: Could not execute '{editor_cmd}'. Is it installed?")
    except OSError as e:
        print(f"Error launching editor: {e}")
