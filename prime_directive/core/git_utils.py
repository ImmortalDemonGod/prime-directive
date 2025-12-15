import subprocess
from typing import List, Dict, Union
import os
import re

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
            check=False,
            timeout=5
        )
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "unknown"

        # Get status (porcelain)
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        status_output = status_proc.stdout
        
        # Parse porcelain output for filenames
        # Porcelain format: XY PATH (XY are status codes, space separated from path)
        # Regex captures: (Group 1: Status XY) (Group 2: Path)
        # Matches start of line, 2 chars for status, 1 space, then the rest is path
        uncommitted_files = []
        for line in status_output.splitlines():
            match = re.match(r"^(.{2}) (.*)$", line)
            if match:
                uncommitted_files.append(match.group(2))
        
        is_dirty = len(uncommitted_files) > 0

        # Get diff stat
        diff_proc = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        diff_stat = diff_proc.stdout.strip()

        return {
            "branch": branch,
            "is_dirty": is_dirty,
            "uncommitted_files": uncommitted_files,
            "diff_stat": diff_stat
        }
    except subprocess.TimeoutExpired:
        return {
            "branch": "timeout",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": "Git command timed out"
        }
    except Exception as e:
        # Fallback for any execution errors
        return {
            "branch": "error",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": str(e)
        }
