import re
import subprocess
from typing import Optional, Tuple


def capture_terminal_state(repo_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Capture the last ~50 lines from a tmux pane and heuristically identify the most recent shell command.
    
    Parameters:
        repo_id (Optional[str]): If provided, target the tmux session named "pd-{repo_id}"; otherwise capture the current pane.
    
    Returns:
        tuple[str, str]: A pair (last_command, output_summary)
            - last_command: Detected last executed command from the captured output, or "unknown" if not detectable.
            - output_summary: The captured pane content (trimmed). If capture fails, one of the fallback messages:
                "No tmux session found or capture failed.",
                "Terminal capture timed out.",
                "tmux not installed.",
                "Unexpected error during terminal capture."
    """
    try:
        # Check if we are inside tmux (basic check, could be more robust)
        # Note: This tool runs inside the IDE, which might not be inside tmux.
        # But the PRD implies this is part of the 'pd' CLI which *might* be
        # running in tmux.
        # We'll try to capture the active pane.

        # Capture last 50 lines
        # -p: output to stdout
        # -S -50: start 50 lines back from end of history
        cmd = ["tmux", "capture-pane", "-p", "-S", "-50"]
        if repo_id:
            cmd.extend(["-t", f"pd-{repo_id}"])

        capture_proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=2
        )

        output_summary = "No tmux session found or capture failed."
        if capture_proc.returncode == 0:
            output_summary = capture_proc.stdout.strip()

        # Best-effort extraction of last executed command from captured output.
        # We keep the existing "unknown" fallback unless we can detect a prompt
        # line.
        last_command = "unknown"
        if (
            output_summary
            and output_summary != "No tmux session found or capture failed."
        ):
            prompt_re = re.compile(r"^\s*(?:\$|❯|>)\s+(.+?)\s*$")
            for line in reversed(output_summary.splitlines()):
                m = prompt_re.match(line)
                if m:
                    candidate = m.group(1).strip()
                    if candidate:
                        last_command = candidate
                        break

        return last_command, output_summary

    except subprocess.TimeoutExpired:
        return "unknown", "Terminal capture timed out."
    except FileNotFoundError:
        # tmux not installed
        return "unknown", "tmux not installed."
    except OSError:
        return "unknown", "Unexpected error during terminal capture."