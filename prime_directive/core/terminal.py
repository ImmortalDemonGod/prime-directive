import asyncio
from asyncio.subprocess import PIPE
import re
from typing import Optional, Tuple


async def _run_tmux_command(
    args: list[str],
    *,
    timeout_seconds: float,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=PIPE,
        stderr=PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise

    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")
    returncode = proc.returncode if proc.returncode is not None else 1
    return returncode, stdout, stderr


async def capture_terminal_state(
    repo_id: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Captures the terminal state from tmux if running inside a tmux session.

    Args:
        repo_id (Optional[str]): If provided, targets the tmux session
            'pd-{repo_id}'. Otherwise captures the current pane.

    Returns:
        tuple[str, str]: (last_command, output_summary)
        - last_command: The last command executed (if available) or "unknown"
        - output_summary: The last ~50 lines of terminal output
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

        returncode, stdout, _stderr = await _run_tmux_command(
            cmd,
            timeout_seconds=2,
        )

        output_summary = "No tmux session found or capture failed."
        if returncode == 0:
            output_summary = stdout.strip()

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

    except asyncio.TimeoutError:
        return "unknown", "Terminal capture timed out."
    except FileNotFoundError:
        # tmux not installed
        return "unknown", "tmux not installed."
    except OSError:
        return "unknown", "Unexpected error during terminal capture."
