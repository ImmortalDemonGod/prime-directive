import json
import os
from typing import Any, Dict, Optional


def get_active_task(repo_path: str) -> Optional[Dict[str, Any]]:
    """
    Selects the highest-priority "in-progress" task from the repository's .taskmaster/tasks/tasks.json.

    If the tasks file is missing, unreadable, or contains invalid JSON, returns None. If the file exists but has not been modified in over 48 hours, a warning is emitted indicating the task data may be stale.

    Parameters:
        repo_path (str): Path to the repository root.

    Returns:
        Optional[Dict[str, Any]]: The task dictionary with the highest priority and largest numeric `id` among tasks whose `status` is `"in-progress"`, or `None` if no such task is found or the file cannot be read/parsed.
    """
    tasks_path = os.path.join(
        repo_path,
        ".taskmaster",
        "tasks",
        "tasks.json",
    )

    if not os.path.exists(tasks_path):
        return None

    # Warn if tasks.json hasn't been modified in >48 hours while the repo
    # is clearly active (git activity is checked by the caller — here we
    # just surface the staleness so the SITREP can flag it).
    _STALE_THRESHOLD_SECONDS = 48 * 3600
    try:
        mtime = os.path.getmtime(tasks_path)
        age_seconds = __import__("time").time() - mtime
        if age_seconds > _STALE_THRESHOLD_SECONDS:
            import warnings

            warnings.warn(
                f"tasks.json has not been updated in "
                f"{age_seconds / 3600:.0f}h — task data may be stale",
                stacklevel=2,
            )
    except OSError:
        pass

    try:
        with open(tasks_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    in_progress_tasks = []

    # Priority mapping
    priority_map = {"high": 3, "medium": 2, "low": 1}

    # Iterate through all tags (e.g., "master")
    for tag_data in data.values():
        if not isinstance(tag_data, dict) or "tasks" not in tag_data:
            continue

        tasks_list = tag_data["tasks"]
        if not isinstance(tasks_list, list):
            continue

        for task in tasks_list:
            if not isinstance(task, dict):
                continue
            if task.get("status") == "in-progress":
                # Add priority value for sorting
                p_str = task.get("priority", "medium").lower()
                p_val = priority_map.get(p_str, 1)
                in_progress_tasks.append((p_val, task))

    if not in_progress_tasks:
        return None

    # Sort by priority (desc) then by ID (desc, assuming higher ID is more
    # recent/relevant).
    # Task ID can be int or str. Let's try to convert to int for sorting if
    # possible.
    def sort_key(item):
        p_val, t = item
        t_id = t.get("id", 0)
        try:
            t_id_val = int(t_id)
        except (ValueError, TypeError):
            t_id_val = 0
        return (p_val, t_id_val)

    in_progress_tasks.sort(key=sort_key, reverse=True)

    return in_progress_tasks[0][1]
