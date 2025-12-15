import pytest
import json
import os
from prime_directive.core.tasks import get_active_task


@pytest.fixture
def mock_repo(tmp_path):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    taskmaster_dir = repo_dir / ".taskmaster" / "tasks"
    taskmaster_dir.mkdir(parents=True)
    return repo_dir


def test_get_active_task_no_file(mock_repo):
    # Test when tasks.json does not exist
    task = get_active_task(str(mock_repo))
    assert task is None


def test_get_active_task_empty_file(mock_repo):
    # Test with empty or invalid JSON
    tasks_file = mock_repo / ".taskmaster" / "tasks" / "tasks.json"
    tasks_file.write_text("{}")

    task = get_active_task(str(mock_repo))
    assert task is None


def test_get_active_task_success(mock_repo):
    # Test finding an in-progress task
    tasks_data = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Task 1",
                    "status": "pending",
                    "priority": "high",
                },
                {
                    "id": 2,
                    "title": "Task 2",
                    "status": "in-progress",
                    "priority": "medium",
                },
                {
                    "id": 3,
                    "title": "Task 3",
                    "status": "done",
                    "priority": "low",
                },
            ]
        }
    }

    tasks_file = mock_repo / ".taskmaster" / "tasks" / "tasks.json"
    tasks_file.write_text(json.dumps(tasks_data))

    task = get_active_task(str(mock_repo))
    assert task is not None
    assert task["id"] == 2
    assert task["title"] == "Task 2"


def test_get_active_task_priority(mock_repo):
    # Test priority sorting (High > Low)
    tasks_data = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Task 1",
                    "status": "in-progress",
                    "priority": "low",
                },
                {
                    "id": 2,
                    "title": "Task 2",
                    "status": "in-progress",
                    "priority": "high",
                },
            ]
        }
    }

    tasks_file = mock_repo / ".taskmaster" / "tasks" / "tasks.json"
    tasks_file.write_text(json.dumps(tasks_data))

    task = get_active_task(str(mock_repo))
    assert task is not None
    assert task["id"] == 2  # High priority should win


def test_get_active_task_recent_id(mock_repo):
    # Test tie-breaking by ID (Higher ID wins)
    tasks_data = {
        "master": {
            "tasks": [
                {
                    "id": 1,
                    "title": "Task 1",
                    "status": "in-progress",
                    "priority": "high",
                },
                {
                    "id": 2,
                    "title": "Task 2",
                    "status": "in-progress",
                    "priority": "high",
                },
            ]
        }
    }

    tasks_file = mock_repo / ".taskmaster" / "tasks" / "tasks.json"
    tasks_file.write_text(json.dumps(tasks_data))

    task = get_active_task(str(mock_repo))
    assert task is not None
    assert task["id"] == 2  # Higher ID should win
