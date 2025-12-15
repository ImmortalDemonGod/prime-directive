import subprocess
from typing import Tuple, Optional

def capture_terminal_state(repo_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Captures the terminal state from tmux if running inside a tmux session.
    
    Args:
        repo_id (Optional[str]): If provided, targets the specific tmux session 'pd-{repo_id}'.
                                 Otherwise captures the current pane.

    Returns:
        tuple[str, str]: (last_command, output_summary)
        - last_command: The last command executed (if available) or "unknown"
        - output_summary: The last ~50 lines of terminal output
    """
    try:
        # Check if we are inside tmux (basic check, could be more robust)
        # Note: This tool runs inside the IDE, which might not be inside tmux. 
        # But the PRD implies this is part of the 'pd' CLI which *might* be running in tmux.
        # We'll try to capture the active pane.
        
        # Capture last 50 lines
        # -p: output to stdout
        # -S -50: start 50 lines back from end of history
        cmd = ["tmux", "capture-pane", "-p", "-S", "-50"]
        if repo_id:
            cmd.extend(["-t", f"pd-{repo_id}"])

        capture_proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=2
        )
        
        output_summary = "No tmux session found or capture failed."
        if capture_proc.returncode == 0:
            output_summary = capture_proc.stdout.strip()
        
        # Capture command history isn't straightforward with just tmux commands without shell integration
        # For now, we'll return a placeholder or try to parse the last prompt line if possible.
        # As per PRD details: "Fallback to 'history | tail -n 1' if not in tmux."
        # History is shell specific and tricky to get from a subprocess.
        last_command = "unknown"
        
        return last_command, output_summary

    except subprocess.TimeoutExpired:
        return "unknown", "Terminal capture timed out."
    except FileNotFoundError:
        # tmux not installed
        return "unknown", "tmux not installed."
    except OSError as e:
        return "error", str(e)
