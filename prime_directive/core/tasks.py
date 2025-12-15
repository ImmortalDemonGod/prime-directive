import json
import os
from typing import Optional, Dict, Any, List

def get_active_task(repo_path: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the active task from the Task Master tasks.json file in the given repository.
    
    Args:
        repo_path (str): Path to the repository root.
        
    Returns:
        Optional[Dict[str, Any]]: The active task dictionary or None if no task is active or file not found.
    """
    tasks_path = os.path.join(repo_path, ".taskmaster", "tasks", "tasks.json")
    
    if not os.path.exists(tasks_path):
        return None
        
    try:
        with open(tasks_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
        
    in_progress_tasks = []
    
    # Priority mapping
    priority_map = {
        "high": 3,
        "medium": 2,
        "low": 1
    }
    
    # Iterate through all tags (e.g., "master")
    for tag_data in data.values():
        if not isinstance(tag_data, dict) or "tasks" not in tag_data:
            continue
            
        for task in tag_data["tasks"]:
            if task.get("status") == "in-progress":
                # Add priority value for sorting
                p_str = task.get("priority", "medium").lower()
                p_val = priority_map.get(p_str, 1)
                in_progress_tasks.append((p_val, task))
    
    if not in_progress_tasks:
        return None
        
    # Sort by priority (descending) and then by ID (descending, assuming higher ID is more recent/relevant)
    # Task ID can be int or str. Let's try to convert to int for sorting if possible.
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
