import subprocess
from typing import List, Dict, Union
import os

def get_status(repo_path: str) -> Dict[str, Union[str, bool, List[str]]]:
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
            "diff_stat": ""
        }

    try:
        # Get current branch
        branch_proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "unknown"

        # Get status (porcelain)
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        status_output = status_proc.stdout.strip()
        is_dirty = len(status_output) > 0
        uncommitted_files = []
        if is_dirty:
            # Parse porcelain output for filenames (simple split might not handle spaces correctly but ok for MVP)
            # Porcelain format: XY PATH
            uncommitted_files = [line[3:] for line in status_output.splitlines() if len(line) > 3]

        # Get diff stat
        diff_proc = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        diff_stat = diff_proc.stdout.strip()

        return {
            "branch": branch,
            "is_dirty": is_dirty,
            "uncommitted_files": uncommitted_files,
            "diff_stat": diff_stat
        }
    except Exception as e:
        # Fallback for any execution errors
        return {
            "branch": "error",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": str(e)
        }
