# Changelog

All notable changes to Prime Directive will be documented in this file.

## [Unreleased]

### Added
- Core CLI commands: `pd doctor`, `pd list`, `pd status`, `pd freeze`, `pd switch`
- SQLite database with async support (SQLModel + aiosqlite)
- Git state capture and status tracking
- Terminal state capture (last command, output summary)
- Task Master integration for active task tracking
- AI-powered SITREP generation via Ollama
- OpenAI fallback with user confirmation guardrails
- Tmux session management per repository
- Context switch orchestrator with atomic semantics
- Auto-freeze daemon with file watcher
- Hydra configuration management
- Shell integration (zsh)
- Comprehensive test suite

### Changed
- Unified configuration to use Hydra exclusively
- Improved tmux session handling (non-blocking attach)

### Security
- Fixed shell injection risk in tmux session creation
- Added budget guardrails for AI API usage

## [0.1.0] - 2024-12-14

### Added
- Initial project structure
- Basic CLI scaffolding
