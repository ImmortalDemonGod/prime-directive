"""
Integration and chaos tests for Prime Directive.

These tests validate end-to-end workflows using mock mode to avoid
external dependencies (tmux, Ollama, OpenAI).
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from typer.testing import CliRunner

from prime_directive.bin.pd import app


runner = CliRunner()


class TestIntegrationMockMode:
    """Integration tests using mock_mode to simulate full workflows."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config with mock_mode enabled."""
        mock_cfg = MagicMock()
        mock_cfg.system.mock_mode = True
        mock_cfg.system.db_path = ":memory:"
        mock_cfg.system.log_path = "/tmp/pd-test.log"
        mock_cfg.system.ai_model = "test-model"
        mock_cfg.system.ai_provider = "ollama"
        mock_cfg.system.ai_fallback_provider = "none"
        mock_cfg.system.ai_fallback_model = "gpt-4o-mini"
        mock_cfg.system.ai_require_confirmation = True
        mock_cfg.system.openai_api_url = (
            "https://api.openai.com/v1/chat/completions"
        )
        mock_cfg.system.openai_timeout_seconds = 10.0
        mock_cfg.system.openai_max_tokens = 150
        mock_cfg.system.ollama_api_url = "http://localhost:11434/api/generate"
        mock_cfg.system.ollama_timeout_seconds = 5.0
        mock_cfg.system.ollama_max_retries = 0
        mock_cfg.system.ollama_backoff_seconds = 0.0
        mock_cfg.system.ai_monthly_budget_usd = 10.0
        mock_cfg.system.ai_cost_per_1k_tokens = 0.002
        mock_cfg.repos = {
            "test-repo": MagicMock(
                id="test-repo",
                path="/tmp/test-repo",
                priority=5,
                active_branch="main",
            )
        }
        return mock_cfg

    def test_freeze_in_mock_mode(self, mock_config):
        """Test that freeze command works in mock mode without real dependencies."""
        with patch(
            "prime_directive.bin.pd.load_config", return_value=mock_config
        ):
            with patch(
                "prime_directive.bin.pd.init_db", new_callable=AsyncMock
            ):
                with patch(
                    "prime_directive.bin.pd.get_session"
                ) as mock_session:
                    # Setup async generator mock
                    async def mock_gen():
                        session = MagicMock()
                        session.add = MagicMock()
                        session.commit = AsyncMock()
                        session.flush = AsyncMock()
                        session.execute = AsyncMock(
                            return_value=MagicMock(
                                scalars=MagicMock(
                                    return_value=MagicMock(
                                        first=MagicMock(return_value=None)
                                    )
                                )
                            )
                        )
                        yield session

                    mock_session.return_value = mock_gen()

                    with patch(
                        "prime_directive.bin.pd.dispose_engine",
                        new_callable=AsyncMock,
                    ):
                        result = runner.invoke(
                            app, ["freeze", "test-repo", "--no-interview"]
                        )

                        # In mock mode, should complete without errors
                        assert result.exit_code == 0 or "MOCK" in result.output

    def test_list_command(self, mock_config):
        """Test list command shows configured repos."""
        with patch(
            "prime_directive.bin.pd.load_config", return_value=mock_config
        ):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "test-repo" in result.output

    def test_doctor_in_mock_mode(self, mock_config):
        """Test doctor command in mock mode."""
        with patch(
            "prime_directive.bin.pd.load_config", return_value=mock_config
        ):
            result = runner.invoke(app, ["doctor"])
            assert result.exit_code == 0
            assert "MOCK MODE" in result.output


class TestChaosOllamaDown:
    """Chaos tests simulating Ollama being unavailable."""

    @pytest.fixture
    def config_ollama_primary(self):
        """Config with Ollama as primary, no fallback."""
        mock_cfg = MagicMock()
        mock_cfg.system.mock_mode = False
        mock_cfg.system.db_path = ":memory:"
        mock_cfg.system.log_path = "/tmp/pd-test.log"
        mock_cfg.system.ai_model = "qwen2.5-coder"
        mock_cfg.system.ai_provider = "ollama"
        mock_cfg.system.ai_fallback_provider = "none"
        mock_cfg.system.ai_fallback_model = "gpt-4o-mini"
        mock_cfg.system.ai_require_confirmation = True
        mock_cfg.system.openai_api_url = (
            "https://api.openai.com/v1/chat/completions"
        )
        mock_cfg.system.openai_timeout_seconds = 10.0
        mock_cfg.system.openai_max_tokens = 150
        mock_cfg.system.ollama_api_url = "http://localhost:11434/api/generate"
        mock_cfg.system.ollama_timeout_seconds = 1.0  # Short timeout for tests
        mock_cfg.system.ollama_max_retries = 0
        mock_cfg.system.ollama_backoff_seconds = 0.0
        mock_cfg.system.ai_monthly_budget_usd = 10.0
        mock_cfg.system.ai_cost_per_1k_tokens = 0.002
        return mock_cfg

    @pytest.mark.asyncio
    async def test_ollama_down_returns_error_message(
        self, config_ollama_primary
    ):
        """When Ollama is down and no fallback, should return error message."""
        import httpx
        from prime_directive.core.scribe import generate_sitrep

        with patch(
            "prime_directive.core.ai_providers.httpx.AsyncClient"
        ) as mock_client:
            # Simulate connection refused
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.return_value = mock_instance

            result = await generate_sitrep(
                repo_id="test-repo",
                git_state="Branch: main\nDirty: False",
                terminal_logs="$ ls\nfile1 file2",
                model=config_ollama_primary.system.ai_model,
                provider=config_ollama_primary.system.ai_provider,
                fallback_provider=config_ollama_primary.system.ai_fallback_provider,
                api_url=config_ollama_primary.system.ollama_api_url,
                timeout_seconds=config_ollama_primary.system.ollama_timeout_seconds,
            )

            # Should return error message, not crash
            assert "Error" in result
            assert "Connection" in result or "connect" in result.lower()

    @pytest.mark.asyncio
    async def test_ollama_down_with_fallback_blocked_by_consent(
        self, config_ollama_primary
    ):
        """When Ollama is down with fallback configured but consent required."""
        import httpx
        from prime_directive.core.scribe import generate_sitrep

        with patch(
            "prime_directive.core.ai_providers.httpx.AsyncClient"
        ) as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.return_value = mock_instance

            result = await generate_sitrep(
                repo_id="test-repo",
                git_state="Branch: main",
                terminal_logs="$ ls",
                provider="ollama",
                fallback_provider="openai",
                require_confirmation=True,  # Consent required
                api_url="http://localhost:11434/api/generate",
                timeout_seconds=1.0,
            )

            # Should indicate consent is required
            assert "confirmation" in result.lower() or "Error" in result


class TestGitParsingEdgeCases:
    """Tests for git parsing edge cases: renames, copies, conflicts."""

    @pytest.mark.asyncio
    async def test_git_status_with_renamed_files(self, tmp_path):
        """Test parsing git status with renamed files."""
        import subprocess
        import os
        from prime_directive.core.git_utils import get_status

        # Create a git repo with a renamed file
        repo = tmp_path / "rename-test"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            capture_output=True,
        )

        # Create and commit a file
        (repo / "old_name.txt").write_text("content")
        subprocess.run(
            ["git", "add", "old_name.txt"], cwd=repo, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=repo, capture_output=True
        )

        # Rename the file
        os.rename(repo / "old_name.txt", repo / "new_name.txt")
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)

        status = await get_status(str(repo))

        assert status["is_dirty"] is True
        # Should detect the rename as changes

    @pytest.mark.asyncio
    async def test_git_status_with_untracked_files(self, tmp_path):
        """Test parsing git status with untracked files."""
        import subprocess
        from prime_directive.core.git_utils import get_status

        repo = tmp_path / "untracked-test"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            capture_output=True,
        )

        # Create initial commit
        (repo / "README.md").write_text("readme")
        subprocess.run(
            ["git", "add", "README.md"], cwd=repo, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=repo, capture_output=True
        )

        # Add untracked file
        (repo / "untracked.txt").write_text("untracked content")

        status = await get_status(str(repo))

        assert status["is_dirty"] is True
        assert "untracked.txt" in status.get("uncommitted_files", [])

    @pytest.mark.asyncio
    async def test_git_status_with_modified_and_staged(self, tmp_path):
        """Test parsing git status with both staged and unstaged changes."""
        import subprocess
        from prime_directive.core.git_utils import get_status

        repo = tmp_path / "mixed-test"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            capture_output=True,
        )

        # Create and commit
        (repo / "file.txt").write_text("original")
        subprocess.run(
            ["git", "add", "file.txt"], cwd=repo, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=repo, capture_output=True
        )

        # Stage a change
        (repo / "file.txt").write_text("staged change")
        subprocess.run(
            ["git", "add", "file.txt"], cwd=repo, capture_output=True
        )

        # Make another unstaged change
        (repo / "file.txt").write_text("staged change + unstaged")

        status = await get_status(str(repo))

        assert status["is_dirty"] is True


class TestBudgetEnforcement:
    """Tests for AI budget enforcement."""

    @pytest.mark.asyncio
    async def test_budget_blocks_when_exceeded(self, tmp_path):
        """Test that budget enforcement blocks calls when exceeded."""
        from prime_directive.core.ai_providers import (
            log_ai_usage,
            check_budget,
        )
        from prime_directive.core.db import init_db

        db_path = str(tmp_path / "budget-test.db")
        await init_db(db_path)

        # Log usage that exceeds budget
        await log_ai_usage(
            db_path=db_path,
            provider="openai",
            model="gpt-4o",
            input_tokens=0,
            output_tokens=10000,
            cost_estimate_usd=15.0,  # Exceeds default $10 budget
            success=True,
        )

        within_budget, current, budget = await check_budget(db_path, 10.0)

        assert within_budget is False
        assert current >= 15.0
        assert budget == 10.0

    @pytest.mark.asyncio
    async def test_budget_allows_when_under(self, tmp_path):
        """Test that budget enforcement allows calls when under budget."""
        from prime_directive.core.ai_providers import (
            log_ai_usage,
            check_budget,
        )
        from prime_directive.core.db import init_db

        db_path = str(tmp_path / "budget-test2.db")
        await init_db(db_path)

        # Log small usage
        await log_ai_usage(
            db_path=db_path,
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=0,
            output_tokens=100,
            cost_estimate_usd=0.0002,
            success=True,
        )

        within_budget, current, budget = await check_budget(db_path, 10.0)

        assert within_budget is True
        assert current < 1.0
