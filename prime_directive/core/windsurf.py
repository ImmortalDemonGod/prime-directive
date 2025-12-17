import subprocess
import shutil


def launch_editor(repo_path: str, editor_cmd: str = "windsurf"):
    """
    Open the repository at repo_path in a new editor instance/window.
    
    Parameters:
        repo_path (str): Filesystem path of the repository to open.
        editor_cmd (str): Editor command to execute (default "windsurf").
    """
    # Verify editor command exists
    if not shutil.which(editor_cmd):
        print(f"Error: Editor command '{editor_cmd}' not found in PATH.")
        return

    try:
        # -n forces a new window/instance, which is standard VS Code / Windsurf
        # CLI behavior
        # This allows multiple projects to be open simultaneously.
        subprocess.Popen([editor_cmd, "-n", repo_path])
    except FileNotFoundError:
        print(f"Error: Could not execute '{editor_cmd}'. Is it installed?")
    except OSError as e:
        print(f"Error launching editor: {e}")