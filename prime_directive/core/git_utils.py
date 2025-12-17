import asyncio
from asyncio.subprocess import PIPE
from typing import List, Dict, Union, Optional
import os
import re


GitStatus = Dict[str, Union[str, bool, List[str]]]


async def _run_git_command(
    repo_path: str,
    args: list[str],
    *,
    timeout_seconds: float,
) -> tuple[int, str, str]:
    """
    Run the given git command in repo_path and capture its exit code, standard output, and standard error.

    Parameters:
        repo_path (str): Filesystem path used as the subprocess working directory
            (the repository root).
        args (list[str]): Command name and arguments to execute (e.g.,
            ["git", "status", "--porcelain"]).
        timeout_seconds (float): Seconds to wait for the process to finish
            before killing it.

    Returns:
        tuple[int, str, str]: (returncode, stdout, stderr) where returncode is
            the process exit code (uses 1 if unavailable), and stdout/stderr
            are decoded strings.

    Raises:
        asyncio.TimeoutError: If the command does not complete within
            timeout_seconds; the subprocess is killed before the exception is
            re-raised.
    """
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
    returncode = proc.returncode if proc.returncode is not None else 1
    return returncode, stdout, stderr


async def get_last_touched(repo_path: str) -> Optional[float]:
    """
    Get the latest modification timestamp among tracked and untracked files in the repository, respecting .gitignore.

    Attempts to list tracked and untracked files via
    `git ls-files -c -o --exclude-standard` and returns the largest filesystem
    modification time (seconds since the epoch) among those files.

    Parameters:
        repo_path (str): Filesystem path to the repository root.

    Returns:
        float | None: The most recent modification time in seconds since the
            epoch, or `None` if the repository is not available, no files are
            found, the git command fails, or an error occurs.
    """
    if not os.path.exists(os.path.join(repo_path, ".git")):
        return None

    try:
        # List all tracked files + others/exclude standard
        # -c: cached
        # -o: others (untracked)
        # --exclude-standard: respect .gitignore
        rc, out, _err = await _run_git_command(
            repo_path,
            ["git", "ls-files", "-c", "-o", "--exclude-standard"],
            timeout_seconds=5,
        )
        if rc != 0:
            return None

        files = [f for f in out.splitlines() if f.strip()]
        if not files:
            return None

        max_mtime = 0.0
        for f in files:
            full_path = os.path.join(repo_path, f)
            try:
                stat = os.stat(full_path)
                if stat.st_mtime > max_mtime:
                    max_mtime = stat.st_mtime
            except OSError:
                pass

        return max_mtime if max_mtime > 0 else None
    except Exception:
        return None


async def get_status(repo_path: str) -> GitStatus:
    """
    Return the repository's git status: current branch, whether there are uncommitted changes, the list of uncommitted file paths, and a textual diff summary.

    Parameters:
        repo_path (str): Filesystem path to the repository root (directory
            containing .git).

    Returns:
        dict: A GitStatus mapping with keys:
            - branch (str): Current branch name, or "unknown"/"timeout"/"error"
              on failure.
            - is_dirty (bool): `True` if there is at least one uncommitted
              file, `False` otherwise.
            - uncommitted_files (list[str]): Paths reported by
              `git status --porcelain` for uncommitted changes.
            - diff_stat (str): Output of `git diff --stat`, or an
              error/timeout message when applicable.
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