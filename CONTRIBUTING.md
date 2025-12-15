# Contributing to Prime Directive

Prime Directive welcomes contributions from the community!

## Requirements

- **Python 3.11+**
- **uv** (recommended) or pip
- **tmux** — For testing tmux integration
- **Ollama** (optional) — For testing AI features locally

## Getting Started

### 1. Fork and Clone

```bash
# Fork via GitHub, then clone your fork
git clone git@github.com:YOUR_USERNAME/prime-directive.git
cd prime-directive
git remote add upstream https://github.com/ImmortalDemonGod/prime-directive
```

### 2. Set Up Development Environment

```bash
# Using uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Or using make
make virtualenv
source .venv/bin/activate
make install
```

### 3. Verify Setup

```bash
# Run tests
pytest

# Check linting
make lint

# Run the CLI
pd doctor
```

## Development Workflow

### Create a Feature Branch

```bash
git checkout -b feature/my-contribution
```

### Make Changes

- Follow existing code patterns and style
- Add tests for new functionality
- Update documentation as needed

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=prime_directive

# Run specific test file
pytest tests/test_cli.py -v
```

### Format and Lint

```bash
# Format code
make fmt

# Run linters
make lint
```

### Commit Changes

This project uses [conventional commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat(cli): add new status command"
git commit -m "fix(db): resolve async session leak"
git commit -m "docs: update installation instructions"
```

### Submit Pull Request

```bash
git push origin feature/my-contribution
```

Then open a PR on GitHub. CI will run automatically.

## Project Structure

```
prime_directive/
├── bin/           # CLI entry points
├── core/          # Core modules
├── conf/          # Hydra configuration
└── system/        # Shell integration

tests/             # pytest test suite
docs/              # Documentation
```

## Code Style

- Use type hints for all functions
- Follow PEP 8 guidelines
- Use async/await for database operations
- Keep functions focused and testable

## Testing Guidelines

- Write tests for all new functionality
- Use `pytest` fixtures for common setup
- Mock external dependencies (Ollama, file system, subprocess)
- Test both success and error paths

## Questions?

Open an issue on GitHub for questions or discussion.
