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

> ⚠️ Prime Directive can't read your mind. Your human insight is the most important piece of context. By default `pd freeze` runs an interactive interview (objective, blocker, next step, notes); use `--no-interview` to provide values via flags.

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
echo 'source ~/.prime-directive/.env' >> ~/.zshrc
source ~/.zshrc

```

#### Shell integration (required for `pd switch`)

Add the Prime Directive shell wrapper to your shell config so `pd switch` can safely manage tmux sessions:

```bash
# If you installed from a local checkout in editable mode, use the repo path:
echo 'source /path/to/prime-directive/prime_directive/system/shell_integration.zsh' >> ~/.zshrc

# Reload
source ~/.zshrc
```

#### Exit Code 88 protocol

`pd switch` uses **exit code `88`** as a handshake signal to the shell:

- **Meaning**: the Python process intentionally exited after computing the target repo/session, and the shell wrapper should perform the tmux attach/switch.
- **Why**: tmux clients should not be parented by the Python process; this avoids fragile process hierarchies and orphaned sessions.

#### Split-process architecture

- **Client (Python)**: runs `pd switch <repo_id>`, freezes/thaws, and exits with `88` when a tmux attach/switch must happen at the shell level.
- **Shell (zsh)**: the `pd()` wrapper in `shell_integration.zsh` traps `88` and runs `tmux attach-session` (outside tmux) or `tmux switch-client` (inside tmux).

See DOC-AUDIT-V1.0 Sections 3.1 and 5.1 for rationale and operational details.

## Quick Start

```bash
# Check system status
pd doctor

# List tracked repositories
pd list

# Freeze current context (interactive interview by default)
pd freeze my-project

# Non-interactive freeze (flags)
pd freeze my-project --no-interview \
  --objective "What you were trying to do" \
  --blocker "What failed / key uncertainty" \
  --next-step "First 10-second action" \
  --note "Any extra notes"

# Switch to another repository (displays your note + AI summary)
pd switch other-project

# View status of a repository
pd status my-project
```

## Terminal Discipline (tmux-first)

Prime Directive’s terminal context capture is tmux-based. For reliable context tracking (especially when switching repos), prefer running stateful workflows inside the repository’s `pd-<repo_id>` tmux session. The `.windsurfrules` file includes a `TERMINAL_DISCIPLINE` rule with a bootstrap snippet that ensures you’re inside tmux before executing terminal commands.

## CLI Commands

| Command | Description |
|---------|-------------|
| `pd doctor` | Check system dependencies and configuration |
| `pd list` | List all tracked repositories with status |
| `pd status` | Show detailed status of all repositories |
| `pd freeze <repo>` | Capture context (interactive interview by default) |
| `pd freeze <repo> --no-interview [--objective ... --blocker ... --next-step ... --note ...]` | Non-interactive freeze using flags |
| `pd freeze <repo> --hq` | Freeze using the configured high-quality model |
| `pd switch <repo>` | Switch to a repository and display saved context |
| `pd sitrep <repo>` | Show latest snapshot SITREP |
| `pd sitrep <repo> --deep-dive` | Generate a longitudinal summary from recent snapshots (requires OpenAI) |
| `pd sitrep <repo> --limit <n>` | Control how many historical snapshots are included |
| `pd metrics [--repo <repo>]` | Show time-to-commit metrics |
| `pd ai-usage` | Show month-to-date AI usage and recent calls |
| `pd install-hooks [repo]` | Install git post-commit hook(s) to log commit events |
| `pd-daemon` | Run inactivity watcher that auto-freezes repos |

## Configuration

Prime Directive uses [Hydra](https://hydra.cc/) for configuration.

To customize your setup, copy the default config to your home directory and edit it:

```bash
mkdir -p ~/.prime-directive
cp /path/to/prime-directive/prime_directive/conf/config.yaml ~/.prime-directive/config.yaml
```

When `~/.prime-directive/config.yaml` exists, `pd` will load it as an override on top of the built-in defaults.

Example:

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
