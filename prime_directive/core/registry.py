from typing import Dict, Optional
from pathlib import Path
import yaml
from pydantic import BaseModel, Field


class SystemConfig(BaseModel):
    editor_cmd: str = Field(default="windsurf")
    ai_model: str = Field(default="qwen2.5-coder")
    db_path: str = Field(default="data/prime.db")


class RepoConfig(BaseModel):
    id: str
    path: str
    priority: int
    active_branch: Optional[str] = None


class Registry(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    repos: Dict[str, RepoConfig] = Field(default_factory=dict)


def load_registry(
    config_path: str = "prime_directive/system/registry.yaml",
) -> Registry:
    """
    Load and parse the registry configuration from a YAML file.
    
    Searches config_path first, then falls back to "system/registry.yaml" in the current working directory.
    If no configuration file is found, returns a default Registry instance. When a file is found, the YAML
    is parsed and converted into a Registry model; repository entries are normalized so a `repos` list is
    converted to a mapping keyed by each repo's `id`, and repo mappings that lack an `id` field receive
    their mapping key as `id`.
    
    Parameters:
        config_path (str): Path to the registry YAML file. Defaults to "prime_directive/system/registry.yaml".
    
    Returns:
        registry (Registry): Registry constructed from the parsed and normalized configuration, or a default
        Registry when no file is present.
    """
    path = Path(config_path)
    if not path.exists():
        # Fallback to looking in system/ relative to cwd if not found
        fallback = Path("system/registry.yaml")
        if fallback.exists():
            path = fallback
        else:
            # Return default if no config found
            return Registry()

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    # Handle list of repos vs dict of repos structure difference in PRD
    # description vs Schema
    # PRD details: repos: [{id: str, path: str...}]
    # But schema in details also implies: repos: {black-box: {...}} in YAML
    # example
    # Let's support the YAML example format (Dict) as it matches "mappings".

    # If the YAML has repos as a list, we convert to dict
    if "repos" in data and isinstance(data["repos"], list):
        repos_dict = {}
        for repo in data["repos"]:
            if "id" in repo:
                repos_dict[repo["id"]] = repo
        data["repos"] = repos_dict
    elif "repos" in data and isinstance(data["repos"], dict):
        # If keys are ids and values are data (without id inside), we need to
        # inject id
        for repo_id, repo_data in data["repos"].items():
            if isinstance(repo_data, dict):
                if "id" not in repo_data:
                    repo_data["id"] = repo_id

    return Registry(**data)