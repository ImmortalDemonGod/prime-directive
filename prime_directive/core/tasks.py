import json
import os
from typing import Optional, Dict, Any


def get_active_task(repo_path: str) -> Optional[Dict[str, Any]]:
    """
    Finds the highest-priority, most-recent task with status "in-progress" from the repository's Task Master tasks.json.
    
    Searches .taskmaster/tasks/tasks.json for tasks whose "status" is "in-progress", ranks them by priority (high > medium > low; unknown priorities treated as lowest) and by numeric task id (higher id considered more recent). Returns None if the file is missing, unreadable, unparseable, or if no in-progress tasks are found.
    
    Parameters:
        repo_path (str): Path to the repository root.
    
    Returns:
        Optional[Dict[str, Any]]: The selected task dictionary, or None if no active task is available.
    """
    tasks_path = os.path.join(
        repo_path,
        ".taskmaster",
        "tasks",
        "tasks.json",
    )

    if not os.path.exists(tasks_path):
        return None

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
        """
        Compute a sortable key for an (priority, task) pair used to order tasks.
        
        Parameters:
            item (tuple): A two-element tuple where the first element is the numeric priority value
                and the second is a task dictionary that may contain an "id" field.
        
        Returns:
            tuple: A pair (priority_value, task_id_int) where `task_id_int` is the task's "id"
            converted to an int when possible, or 0 if conversion fails or the id is missing.
        """
        p_val, t = item
        t_id = t.get("id", 0)
        try:
            t_id_val = int(t_id)
        except (ValueError, TypeError):
            t_id_val = 0
        return (p_val, t_id_val)

    in_progress_tasks.sort(key=sort_key, reverse=True)

    return in_progress_tasks[0][1]