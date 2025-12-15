from dataclasses import dataclass, field
from typing import Dict, Optional
from hydra.core.config_store import ConfigStore

@dataclass
class SystemConfig:
    editor_cmd: str = "windsurf"
    ai_model: str = "qwen2.5-coder"
    db_path: str = "data/prime.db"

@dataclass
class RepoConfig:
    id: str
    path: str
    priority: int
    active_branch: str = "main"

@dataclass
class PrimeConfig:
    system: SystemConfig = field(default_factory=SystemConfig)
    repos: Dict[str, RepoConfig] = field(default_factory=dict)

def register_configs():
    cs = ConfigStore.instance()
    cs.store(name="base_config", node=PrimeConfig)
