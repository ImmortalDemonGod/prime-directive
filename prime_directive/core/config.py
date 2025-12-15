from dataclasses import dataclass, field
from typing import Dict, Optional
from hydra.core.config_store import ConfigStore

@dataclass
class SystemConfig:
    editor_cmd: str = "windsurf"
    ai_model: str = "qwen2.5-coder"
    ai_provider: str = "ollama"
    ai_fallback_provider: str = "none"
    ai_fallback_model: str = "gpt-4o-mini"
    ai_require_confirmation: bool = True
    openai_api_url: str = "https://api.openai.com/v1/chat/completions"
    openai_timeout_seconds: float = 10.0
    openai_max_tokens: int = 150
    ollama_api_url: str = "http://localhost:11434/api/generate"
    ollama_timeout_seconds: float = 5.0
    ollama_max_retries: int = 2
    ollama_backoff_seconds: float = 0.5
    db_path: str = "data/prime.db"
    log_path: str = "data/logs/pd.log"
    mock_mode: bool = False

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
