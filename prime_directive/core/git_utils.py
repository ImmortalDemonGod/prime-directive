import asyncio
from asyncio.subprocess import PIPE
from typing import List, Dict, Union
import os
import re


GitStatus = Dict[str, Union[str, bool, List[str]]]


async def _run_git_command(
    repo_path: str,
    args: list[str],
    *,
    timeout_seconds: float,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=repo_path,
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
    return proc.returncode, stdout, stderr


async def get_status(repo_path: str) -> GitStatus:
    """
    Capture git status for a repository.

    Returns:
        dict: {
            'branch': str,
            'is_dirty': bool,
            'uncommitted_files': list[str],
            'diff_stat': str
        }
    """
    if not os.path.exists(os.path.join(repo_path, ".git")):
        return {
            "branch": "unknown",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": "",
        }

    try:
        # Get current branch
        rc, branch_out, _branch_err = await _run_git_command(
            repo_path,
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            timeout_seconds=5,
        )
        if rc == 0:
            branch = branch_out.strip()
        else:
            branch = "unknown"

        # Get status (porcelain)
        _rc, status_output, _status_err = await _run_git_command(
            repo_path,
            ["git", "status", "--porcelain"],
            timeout_seconds=5,
        )

        # Parse porcelain output for filenames
        # Porcelain format: XY PATH (XY are status codes, space separated from
        # path)
        # Regex captures: (Group 1: Status XY) (Group 2: Path)
        # Matches start of line, 2 chars for status, 1 space, then the rest is
        # path
        uncommitted_files = []
        for line in status_output.splitlines():
            match = re.match(r"^(.{2}) (.*)$", line)
            if match:
                uncommitted_files.append(match.group(2))

        is_dirty = len(uncommitted_files) > 0

        # Get diff stat
        _rc, diff_out, _diff_err = await _run_git_command(
            repo_path,
            ["git", "diff", "--stat"],
            timeout_seconds=5,
        )
        diff_stat = diff_out.strip()

        return {
            "branch": branch,
            "is_dirty": is_dirty,
            "uncommitted_files": uncommitted_files,
            "diff_stat": diff_stat,
        }
    except asyncio.TimeoutError:
        return {
            "branch": "timeout",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": "Git command timed out",
        }
    except Exception as e:
        # Fallback for any execution errors
        return {
            "branch": "error",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": str(e),
        }
