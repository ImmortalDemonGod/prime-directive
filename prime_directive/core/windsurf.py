import subprocess
import shutil


def launch_editor(repo_path: str, editor_cmd: str = "windsurf"):
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
        # -n forces a new window/instance, which is standard VS Code / Windsurf CLI behavior
        # This allows multiple projects to be open simultaneously.
        subprocess.Popen([editor_cmd, "-n", repo_path])
    except FileNotFoundError:
        print(f"Error: Could not execute '{editor_cmd}'. Is it installed?")
    except OSError as e:
        print(f"Error launching editor: {e}")
