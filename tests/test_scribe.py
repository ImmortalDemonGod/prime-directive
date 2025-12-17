import pytest
from unittest.mock import patch, Mock, AsyncMock

import httpx

from prime_directive.core.scribe import generate_sitrep


async def test_generate_sitrep_success():
    mock_response = Mock()
    mock_response.json.return_value = {
        "response": "SITREP: All systems go. Next: Deploy."
    }
    mock_response.raise_for_status.return_value = None

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_post:
        result = await generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="echo hello",
            active_task={
                "id": 1,
                "title": "Test Task",
                "description": "Testing",
            },
        )

        assert result == "SITREP: All systems go. Next: Deploy."
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "qwen2.5-coder"
        assert "Test Task" in kwargs["json"]["prompt"]
        assert "Chief of Staff" in kwargs["json"]["system"]


async def test_generate_sitrep_timeout():
    req = httpx.Request("POST", "http://localhost:11434/api/generate")
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ReadTimeout("Timed out", request=req),
    ):
        result = await generate_sitrep(
            repo_id="test-repo", git_state="clean", terminal_logs="loading..."
        )
        assert "Error generating SITREP" in result
        assert "Timed out" in result


async def test_generate_sitrep_connection_error():
    req = httpx.Request("POST", "http://localhost:11434/api/generate")
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused", request=req),
    ):
        result = await generate_sitrep(
            repo_id="test-repo", git_state="clean", terminal_logs="loading..."
        )
        assert "Error generating SITREP" in result
        assert "Connection refused" in result


async def test_generate_sitrep_retries_then_success():
    mock_response = Mock()
    mock_response.json.return_value = {
        "response": "SITREP: Recovered. Next: Continue."
    }
    mock_response.raise_for_status.return_value = None

    req = httpx.Request("POST", "http://localhost:11434/api/generate")

    side_effects = [
        httpx.ReadTimeout("Timed out", request=req),
        mock_response,
    ]

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=side_effects,
    ) as mock_post:
        result = await generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="loading...",
            max_retries=1,
            backoff_seconds=0.0,
        )

        assert result == "SITREP: Recovered. Next: Continue."
        assert mock_post.call_count == 2


async def test_generate_sitrep_fallback_requires_confirmation():
    req = httpx.Request("POST", "http://localhost:11434/api/generate")
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ReadTimeout("Timed out", request=req),
    ):
        result = await generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="loading...",
            fallback_provider="openai",
            require_confirmation=True,
        )
        assert "Error generating SITREP" in result
        assert "requires confirmation" in result


async def test_generate_sitrep_fallback_openai_success():
    req = httpx.Request("POST", "http://localhost:11434/api/generate")
    with (
        patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused", request=req),
        ),
        patch(
            "prime_directive.core.scribe.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.scribe.generate_openai_chat",
            new_callable=AsyncMock,
            return_value="SITREP: Fallback ok.",
        ) as mock_openai,
    ):
        result = await generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="loading...",
            fallback_provider="openai",
            fallback_model="gpt-4o-mini",
            require_confirmation=False,
        )
        assert result == "SITREP: Fallback ok."
        mock_openai.assert_called_once()
        _args, kwargs = mock_openai.call_args
        assert "Chief of Staff" in kwargs["system"]
