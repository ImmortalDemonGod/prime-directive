# Prime Directive

[![CI](https://github.com/ImmortalDemonGod/prime-directive/actions/workflows/main.yml/badge.svg)](https://github.com/ImmortalDemonGod/prime-directive/actions/workflows/main.yml)
[![codecov](https://codecov.io/gh/ImmortalDemonGod/prime-directive/branch/main/graph/badge.svg)](https://codecov.io/gh/ImmortalDemonGod/prime-directive)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**Prime Directive** is an AI-powered context preservation system for developers who work across multiple repositories. It automatically captures and restores your development context—git state, terminal history, active tasks, and AI-generated situational reports—so you can seamlessly switch between projects without losing your train of thought.

## Features

- **Context Freezing** — Capture git status, terminal state, active tasks, and generate AI summaries before switching projects
- **Context Restoration** — Instantly restore your previous context when returning to a project
- **Multi-Repo Management** — Track and switch between multiple repositories with a unified CLI
- **AI-Powered SITREPs** — Generate situational reports using Ollama (local) or OpenAI (fallback)
- **Tmux Integration** — Automatic tmux session management per repository
- **Task Master Integration** — Track active tasks from `.taskmaster/tasks.json`
- **Daemon Mode** — Auto-freeze on inactivity to ensure context is always saved

## Installation

### Prerequisites

- **Python 3.11+**
- **tmux** — For terminal session management
- **Ollama** (recommended) — For local AI-powered SITREP generation

```bash
# Install system dependencies (macOS)
brew install tmux ollama

# Start Ollama and pull a model
brew services start ollama
ollama pull qwen2.5-coder
```

### Install Prime Directive

```bash
# Using uv (recommended)
uv pip install -e .

# Or using pip
pip install -e .
```

## Quick Start

```bash
# Check system status
pd doctor

# List tracked repositories
pd list

# Freeze current context before switching
pd freeze my-project

# Switch to another repository (auto-freezes current, restores target)
pd switch other-project

# View status of a repository
pd status my-project
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `pd doctor` | Check system dependencies and configuration |
| `pd list` | List all tracked repositories with status |
| `pd status <repo>` | Show detailed status of a repository |
| `pd freeze <repo>` | Capture and save current context |
| `pd switch <repo>` | Switch to a repository (freeze current + restore target) |

## Configuration

Prime Directive uses [Hydra](https://hydra.cc/) for configuration. Edit `prime_directive/conf/config.yaml`:

```yaml
system:
  db_path: data/prime.db
  log_level: INFO
  editor_cmd: windsurf
  ai_model: qwen2.5-coder
  ollama_api_url: http://localhost:11434/api/generate
  ai_fallback_provider: openai
  ai_require_confirmation: true
```

### Environment Variables

Create a `.env` file for sensitive configuration:

```bash
# Optional: OpenAI fallback (when Ollama is unavailable)
OPENAI_API_KEY=sk-...
```

## Architecture

```
prime_directive/
├── bin/
│   ├── pd.py           # Main CLI (Typer)
│   └── pd_daemon.py    # Auto-freeze daemon
├── core/
│   ├── config.py       # Hydra configuration
│   ├── db.py           # SQLModel database (async SQLite)
│   ├── git_utils.py    # Git state capture
│   ├── scribe.py       # AI SITREP generation
│   ├── tasks.py        # Task Master integration
│   ├── terminal.py     # Terminal state capture
│   ├── tmux.py         # Tmux session management
│   └── orchestrator.py # Context switch orchestration
└── conf/
    └── config.yaml     # Default Hydra config
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run linter
make lint

# Format code
make fmt
```

## License

MIT License - see [LICENSE](LICENSE) for details.
