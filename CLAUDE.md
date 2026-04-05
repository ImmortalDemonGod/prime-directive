# Claude Code Rules

## Commits

- Use atomic commits: one file per commit.
- Do not add Claude co-author tags to commit messages.
- Use `git -c commit.gpgsign=false` for all commits (GPG agent hangs in non-interactive sessions).

## Before Pushing

- Run full lint locally before every push: `uv run flake8 prime_directive/` + `uv run black --check prime_directive/ tests/` + `uv run mypy --ignore-missing-imports prime_directive/`
- Black config lives in `pyproject.toml` (`[tool.black]`, target-version py311). Do not pass `-l 79` on the CLI — it's in the config.
- After merging any external PR (e.g. CodeRabbit docstrings), immediately run `uv run black prime_directive/ tests/` and fix trailing whitespace before pushing.

## PR Readiness Checklist

- CI must be fully green (all jobs) — do not declare "ready" until verified via `gh run view`
- Request CodeRabbit full review (`@coderabbitai full review`) and docstrings (`@coderabbitai generate docstrings`)
- Merge docstrings PR into feature branch before final merge
- Add AIV-Lite verification packet to PR description body
- File GitHub issues for all unresolved findings and follow-up work
- Save PR artifacts ZIP to `/Volumes/Totallynotaharddrive/WEEKLY_PRS_FOR_NOTEBOOK_LLM/`
- GitHub rebase-merge fails at 100+ commits — use regular merge for large PRs
