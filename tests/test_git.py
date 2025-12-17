import pytest
import shutil
import subprocess
import time
import os
from pathlib import Path
from prime_directive.core.git_utils import get_status, get_last_touched


@pytest.fixture
def temp_git_repo(tmp_path):
    """
    Create a temporary Git repository (inside the provided tmp_path) with a single initial commit and return its path.
    
    Parameters:
        tmp_path (pathlib.Path): Temporary directory provided by pytest used as the parent directory for the repository.
    
    Returns:
        pathlib.Path: Path to the created Git repository directory containing the initial commit.
    """
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "you@example.com"],
        cwd=repo_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Your Name"], cwd=repo_path, check=True
    )

    # Create initial commit
    (repo_path / "README.md").write_text("Initial content")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
    )

    return repo_path


async def test_get_status_clean(temp_git_repo):
    status = await get_status(str(temp_git_repo))
    assert status["branch"] in ["main", "master"]
    assert status["is_dirty"] is False
    assert status["uncommitted_files"] == []
    assert status["diff_stat"] == ""


async def test_get_status_dirty(temp_git_repo):
    # Modify a file
    (temp_git_repo / "README.md").write_text("Modified content")

    status = await get_status(str(temp_git_repo))
    assert status["is_dirty"] is True
    assert "README.md" in status["uncommitted_files"]
    assert "README.md" in status["diff_stat"]


async def test_get_status_new_file(temp_git_repo):
    # Add a new file
    (temp_git_repo / "new_file.txt").write_text("New file")

    # Untracked files show up in status --porcelain
    status = await get_status(str(temp_git_repo))
    assert status["is_dirty"] is True
    assert "new_file.txt" in status["uncommitted_files"]


async def test_get_status_non_git(tmp_path):
    # Just a regular folder
    non_git_path = tmp_path / "regular_folder"
    non_git_path.mkdir()

    status = await get_status(str(non_git_path))
    assert status["branch"] == "unknown"
    assert status["is_dirty"] is False


async def test_get_last_touched(temp_git_repo):
    new_file = temp_git_repo / "touched.txt"
    new_file.write_text("content")

    ts = await get_last_touched(str(temp_git_repo))
    assert ts is not None

    # Make touched.txt unambiguously the most recently modified file
    future_time = time.time() + 1000
    os.utime(new_file, (future_time, future_time))

    ts_future = await get_last_touched(str(temp_git_repo))
    assert ts_future is not None
    assert abs(ts_future - future_time) < 2.0

    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("touched.txt\n")

    ignored_time = time.time() + 2000
    os.utime(gitignore, (ignored_time, ignored_time))

    ts_ignored = await get_last_touched(str(temp_git_repo))
    assert ts_ignored is not None
    assert abs(ts_ignored - ignored_time) < 2.0

    future_time_2 = time.time() + 3000
    os.utime(new_file, (future_time_2, future_time_2))

    ts_ignored_again = await get_last_touched(str(temp_git_repo))
    assert ts_ignored_again is not None
    assert abs(ts_ignored_again - ignored_time) < 2.0


async def test_get_last_touched_no_git(tmp_path):
    ts = await get_last_touched(str(tmp_path))
    assert ts is None