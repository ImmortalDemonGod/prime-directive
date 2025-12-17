import subprocess
import shutil
from typing import Optional


def launch_editor(
    repo_path: str,
    editor_cmd: str = "windsurf",
    editor_args: Optional[list[str]] = None,
):
    """
    Open the given repository path in a local editor process.
    
    Verifies that `editor_cmd` exists on the system PATH, constructs a command by combining `editor_cmd`, `editor_args` (defaulting to ["-n"] when not provided), and `repo_path`, then starts the editor as a subprocess. If the command is not found or the process cannot be started, an error message is printed and the function returns without raising.
    
    Parameters:
        repo_path (str): Filesystem path of the repository to open in the editor.
        editor_cmd (str): Executable name or command used to launch the editor (default: "windsurf").
        editor_args (Optional[list[str]]): Additional command-line arguments to pass to the editor; when omitted, defaults to ["-n"].
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