import pytest
import shutil
import subprocess
from pathlib import Path
from prime_directive.core.git_utils import get_status

@pytest.fixture
def temp_git_repo(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    
    # Initialize git
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "you@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Your Name"], cwd=repo_path, check=True)
    
    # Create initial commit
    (repo_path / "README.md").write_text("Initial content")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
    
    return repo_path

def test_get_status_clean(temp_git_repo):
    status = get_status(str(temp_git_repo))
    assert status["branch"] in ["main", "master"]
    assert status["is_dirty"] is False
    assert status["uncommitted_files"] == []
    assert status["diff_stat"] == ""

def test_get_status_dirty(temp_git_repo):
    # Modify a file
    (temp_git_repo / "README.md").write_text("Modified content")
    
    status = get_status(str(temp_git_repo))
    assert status["is_dirty"] is True
    assert "README.md" in status["uncommitted_files"]
    assert "README.md" in status["diff_stat"]

def test_get_status_new_file(temp_git_repo):
    # Add a new file
    (temp_git_repo / "new_file.txt").write_text("New file")
    
    # Untracked files show up in status --porcelain
    status = get_status(str(temp_git_repo))
    assert status["is_dirty"] is True
    assert "new_file.txt" in status["uncommitted_files"]

def test_get_status_non_git(tmp_path):
    # Just a regular folder
    non_git_path = tmp_path / "regular_folder"
    non_git_path.mkdir()
    
    status = get_status(str(non_git_path))
    assert status["branch"] == "unknown"
    assert status["is_dirty"] is False
