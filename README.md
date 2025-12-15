# Prime Directive

[![CI](https://github.com/ImmortalDemonGod/prime-directive/actions/workflows/main.yml/badge.svg)](https://github.com/ImmortalDemonGod/prime-directive/actions/workflows/main.yml)
[![codecov](https://codecov.io/gh/ImmortalDemonGod/prime-directive/branch/main/graph/badge.svg)](https://codecov.io/gh/ImmortalDemonGod/prime-directive)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**Prime Directive** is an AI-powered context preservation system for developers who work across multiple repositories. It automatically captures and restores your development context—git state, terminal history, active tasks, and AI-generated situational reports—so you can seamlessly switch between projects without losing your train of thought.

## The Core User Story: "Monday Morning Warp"

You stop working on `rna-predict` on Friday night. You spend the weekend on `black-box`. Monday morning, you return to `rna-predict`:

```bash
$ pd switch rna-predict

>>> WARPING TO RNA-PREDICT >>>

 SITREP 
>>> HUMAN NOTE: Fixing the SE(3) equivariant loss - test_rotation_invariance fails
>>> AI SUMMARY: Working on equivariant.py line 142, the normalization epsilon is hardcoded...
>>> TIMESTAMP: Friday 22:45
```

**The Amnesia Test**: Can you commit valid code within 5 minutes of `pd switch`? If yes, the system is working.

> ⚠️ The `--note` flag is **mandatory** because AI can't read your mind. Your human insight is the most important piece of context.

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
# Install globally (recommended - works from any terminal)
uv tool install /path/to/prime-directive

# Or install in development mode
uv pip install -e .
```

### Post-Installation Setup

```bash
# Create centralized config directory
mkdir -p ~/.prime-directive

# Copy your API keys
echo 'OPENAI_API_KEY="sk-your-key-here"' > ~/.prime-directive/.env

# Add to your shell (required for API keys)
echo 'export OPENAI_API_KEY="$(grep OPENAI_API_KEY ~/.prime-directive/.env | cut -d= -f2 | tr -d \")"' >> ~/.zshrc
source ~/.zshrc
```

## Quick Start

```bash
# Check system status
pd doctor

# List tracked repositories
pd list

# Freeze current context (--note is REQUIRED)
pd freeze my-project --note "What you were actually working on"

# Switch to another repository (displays your note + AI summary)
pd switch other-project

# View status of a repository
pd status my-project
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `pd doctor` | Check system dependencies and configuration |
| `pd list` | List all tracked repositories with status |
| `pd status` | Show detailed status of all repositories |
| `pd freeze <repo> --note "..."` | Capture context with your human note (required) |
| `pd switch <repo>` | Switch to a repository and display saved context |

## Configuration

Prime Directive uses [Hydra](https://hydra.cc/) for configuration. Edit `prime_directive/conf/config.yaml`:

```yaml
system:
  editor_cmd: windsurf
  ai_model: gpt-4o-mini          # Model to use for SITREP
  ai_provider: openai            # Primary provider: "openai" or "ollama"
  db_path: ~/.prime-directive/data/prime.db
  log_path: ~/.prime-directive/logs/pd.log

repos:
  my-project:
    id: my-project
    path: /path/to/my-project
    priority: 10
    active_branch: main
```

### Data Storage

All data is stored in `~/.prime-directive/`:

| Path | Purpose |
|------|---------|
| `~/.prime-directive/.env` | API keys (OPENAI_API_KEY) |
| `~/.prime-directive/data/prime.db` | Snapshots database |
| `~/.prime-directive/logs/pd.log` | Application logs |

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
