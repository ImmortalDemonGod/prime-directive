from unittest.mock import AsyncMock, patch

from prime_directive.core.dossier_ai import generate_theme_suggestions_with_ai


async def test_generate_theme_suggestions_with_ai_openai_success():
    with (
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
            new_callable=AsyncMock,
            return_value=(
                '{"suggestions":[{"tag":"gradient-debugging","occurrences":3,"evidence":"3 snapshots mention gradient debugging","confidence":0.7}]}',
                {"prompt_tokens": 12, "completion_tokens": 8},
            ),
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                snapshot_texts=[
                    "Investigating gradient debugging for diffusion training instability.",
                    "Need gradient debugging before next training run.",
                ],
                existing_tags=[],
                model="gpt-4o-mini",
                provider="openai",
                fallback_provider="none",
                fallback_model="gpt-4o-mini",
                require_confirmation=False,
                openai_api_url="https://api.openai.com/v1/chat/completions",
                openai_timeout_seconds=10.0,
                openai_max_tokens=150,
                api_url="http://localhost:11434/api/generate",
                timeout_seconds=5.0,
                max_retries=0,
                backoff_seconds=0.0,
                db_path=None,
                monthly_budget_usd=10.0,
                cost_per_1k_tokens=0.002,
            )
        )

    assert error is None
    assert [item.tag for item in suggestions] == ["gradient-debugging"]
    assert metadata is not None
    assert metadata.provider == "openai"
    assert metadata.input_tokens == 12
    assert metadata.output_tokens == 8


async def test_generate_theme_suggestions_with_ai_blocks_when_budget_exceeded():
    with (
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.check_budget",
            new_callable=AsyncMock,
            return_value=(False, 12.0, 10.0),
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                snapshot_texts=[
                    "Investigating gradient debugging for diffusion training instability."
                ],
                existing_tags=[],
                model="gpt-4o-mini",
                provider="openai",
                fallback_provider="none",
                fallback_model="gpt-4o-mini",
                require_confirmation=False,
                openai_api_url="https://api.openai.com/v1/chat/completions",
                openai_timeout_seconds=10.0,
                openai_max_tokens=150,
                api_url="http://localhost:11434/api/generate",
                timeout_seconds=5.0,
                max_retries=0,
                backoff_seconds=0.0,
                db_path="/tmp/prime.db",
                monthly_budget_usd=10.0,
                cost_per_1k_tokens=0.002,
            )
        )

    assert suggestions == []
    assert metadata is None
    assert error is not None
    assert "Monthly budget exceeded" in error


import json
from unittest.mock import MagicMock

import httpx

from prime_directive.core.dossier_ai import (
    AIAnalysisMetadata,
    _count_tokens,
    _extract_json_text,
    _parse_theme_suggestions_response,
    _log_usage,
)

# ── Shared kwargs for generate_theme_suggestions_with_ai ──

_BASE_KWARGS = dict(
    snapshot_texts=[
        "Snapshot about distributed tracing.",
        "Another about distributed tracing.",
    ],
    existing_tags=[],
    model="llama3",
    provider="ollama",
    fallback_provider="none",
    fallback_model="gpt-4o-mini",
    require_confirmation=False,
    openai_api_url="https://api.openai.com/v1/chat/completions",
    openai_timeout_seconds=10.0,
    openai_max_tokens=150,
    api_url="http://localhost:11434/api/generate",
    timeout_seconds=5.0,
    max_retries=0,
    backoff_seconds=0.0,
    db_path=None,
    monthly_budget_usd=10.0,
    cost_per_1k_tokens=0.002,
)


# ── _count_tokens ──


def test_count_tokens_with_tiktoken():
    """tiktoken happy path."""
    count = _count_tokens("hello world", "gpt-4o-mini")
    assert isinstance(count, int)
    assert count > 0


def test_count_tokens_unknown_model_falls_back_to_cl100k():
    """Unknown model falls back to cl100k_base."""
    count = _count_tokens("hello world", "totally-unknown-model-xyz")
    assert isinstance(count, int)
    assert count > 0


def test_count_tokens_returns_positive_for_known_model():
    """Known model returns a positive token count."""
    count = _count_tokens("hello world this is a test", "gpt-4")
    assert isinstance(count, int)
    assert count > 0


# ── _extract_json_text ──


def test_extract_json_text_strips_code_fence():
    raw = '```json\n{"suggestions":[]}\n```'
    assert _extract_json_text(raw) == '{"suggestions":[]}'


def test_extract_json_text_strips_code_fence_no_lang():
    raw = '```\n{"suggestions":[]}\n```'
    assert _extract_json_text(raw) == '{"suggestions":[]}'


# ── _parse_theme_suggestions_response ──


def test_parse_response_list_format():
    """Payload is a list directly."""
    raw = json.dumps(
        [
            {
                "tag": "distributed-tracing",
                "occurrences": 3,
                "evidence": "test",
                "confidence": 0.8,
            }
        ]
    )
    result = _parse_theme_suggestions_response(raw, [], 5)
    assert len(result) == 1
    assert result[0].tag == "distributed-tracing"


def test_parse_response_invalid_type_raises():
    """Payload is neither dict nor list."""
    import pytest

    with pytest.raises(ValueError, match="must be a JSON object or list"):
        _parse_theme_suggestions_response('"just a string"', [], 5)


def test_parse_response_skips_non_dict_items():
    """Non-dict items in suggestions list are skipped."""
    raw = json.dumps(
        {
            "suggestions": [
                "not-a-dict",
                {
                    "tag": "valid",
                    "occurrences": 1,
                    "evidence": "e",
                    "confidence": 0.5,
                },
            ]
        }
    )
    result = _parse_theme_suggestions_response(raw, [], 5)
    assert len(result) == 1
    assert result[0].tag == "valid"


def test_parse_response_skips_existing_tags():
    """Existing tags are excluded."""
    raw = json.dumps(
        {
            "suggestions": [
                {
                    "tag": "existing-tag",
                    "occurrences": 2,
                    "evidence": "e",
                    "confidence": 0.6,
                },
                {
                    "tag": "new-tag",
                    "occurrences": 2,
                    "evidence": "e",
                    "confidence": 0.6,
                },
            ]
        }
    )
    result = _parse_theme_suggestions_response(raw, ["existing-tag"], 5)
    assert len(result) == 1
    assert result[0].tag == "new-tag"


# ── generate_theme_suggestions_with_ai: empty input ──


async def test_generate_returns_empty_for_blank_snapshots():
    suggestions, metadata, error = await generate_theme_suggestions_with_ai(
        **{**_BASE_KWARGS, "snapshot_texts": ["", "  "]}
    )
    assert suggestions == []
    assert metadata is None
    assert error is None


# ── generate_theme_suggestions_with_ai: prompt truncation ──


async def test_generate_truncates_long_prompt():
    long_text = "x" * 20000
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        return_value='{"suggestions":[]}',
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{
                    **_BASE_KWARGS,
                    "snapshot_texts": [long_text],
                    "max_prompt_chars": 100,
                }
            )
        )
    assert error is None


# ── generate_theme_suggestions_with_ai: Ollama primary success ──


async def test_generate_ollama_primary_success():
    """Ollama primary provider happy path (no usage dict)."""
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        return_value='{"suggestions":[{"tag":"distributed-tracing","occurrences":2,"evidence":"multiple mentions","confidence":0.8}]}',
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(**_BASE_KWARGS)
        )

    assert error is None
    assert len(suggestions) == 1
    assert suggestions[0].tag == "distributed-tracing"
    assert metadata is not None
    assert metadata.provider == "ollama"
    assert metadata.cost_estimate_usd == 0.0


# ── finalize_success: Ollama counts tokens locally ──


async def test_finalize_success_ollama_counts_tokens_locally():
    """When usage is None, _count_tokens is called."""
    with (
        patch(
            "prime_directive.core.dossier_ai.generate_ollama",
            new_callable=AsyncMock,
            return_value='{"suggestions":[]}',
        ),
        patch(
            "prime_directive.core.dossier_ai._count_tokens",
            return_value=42,
        ) as mock_count,
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(**_BASE_KWARGS)
        )

    assert mock_count.call_count == 2
    assert metadata.input_tokens == 42
    assert metadata.output_tokens == 42


# ── finalize_success with usage dict ──


async def test_finalize_success_with_usage_dict():
    """Usage dict sets tokens directly and logs success."""
    with (
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.check_budget",
            new_callable=AsyncMock,
            return_value=(True, 0.0, 10.0),
        ),
        patch(
            "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
            new_callable=AsyncMock,
            return_value=(
                '{"suggestions":[]}',
                {"prompt_tokens": 100, "completion_tokens": 50},
            ),
        ),
        patch(
            "prime_directive.core.dossier_ai.log_ai_usage",
            new_callable=AsyncMock,
        ) as mock_log,
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{
                    **_BASE_KWARGS,
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "db_path": "/tmp/test.db",
                }
            )
        )

    assert error is None
    assert metadata.input_tokens == 100
    assert metadata.output_tokens == 50
    assert metadata.cost_estimate_usd > 0
    mock_log.assert_called_once()
    assert mock_log.call_args[1]["success"] is True


# ── finalize_error path ──


async def test_finalize_error_logs_failure_and_returns_error():
    """Ollama failure with no fallback returns error."""
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(**_BASE_KWARGS)
        )

    assert suggestions == []
    assert metadata is None
    assert "connection refused" in error


# ── finalize_error on parse failure ──


async def test_finalize_error_on_parse_failure():
    """Parse error in finalize_success delegates to finalize_error."""
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        return_value="not valid json at all {{{",
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(**_BASE_KWARGS)
        )

    assert suggestions == []
    assert metadata is None
    assert error is not None


# ── OpenAI primary: no API key ──


async def test_openai_primary_no_api_key():
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value=None,
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{
                    **_BASE_KWARGS,
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                }
            )
        )

    assert suggestions == []
    assert "OPENAI_API_KEY not set" in error


# ── OpenAI primary: HTTP error ──


async def test_openai_primary_http_error():
    with (
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("api down"),
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{
                    **_BASE_KWARGS,
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                }
            )
        )

    assert suggestions == []
    assert "api down" in error


# ── Ollama fails, fallback to OpenAI ──


async def test_ollama_fails_fallback_to_openai_success():
    """Ollama fails, fallback_provider=openai, OpenAI succeeds."""
    with (
        patch(
            "prime_directive.core.dossier_ai.generate_ollama",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("ollama down"),
        ),
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
            new_callable=AsyncMock,
            return_value=(
                '{"suggestions":[{"tag":"fallback-tag","occurrences":2,"evidence":"test","confidence":0.9}]}',
                {"prompt_tokens": 20, "completion_tokens": 10},
            ),
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{**_BASE_KWARGS, "fallback_provider": "openai"}
            )
        )

    assert error is None
    assert len(suggestions) == 1
    assert suggestions[0].tag == "fallback-tag"
    assert metadata.provider == "openai"
    assert metadata.model == "gpt-4o-mini"


async def test_ollama_fails_fallback_requires_confirmation():
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("ollama down"),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{
                    **_BASE_KWARGS,
                    "fallback_provider": "openai",
                    "require_confirmation": True,
                }
            )
        )

    assert suggestions == []
    assert "requires confirmation" in error


async def test_ollama_fails_fallback_no_api_key():
    with (
        patch(
            "prime_directive.core.dossier_ai.generate_ollama",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("ollama down"),
        ),
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value=None,
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{**_BASE_KWARGS, "fallback_provider": "openai"}
            )
        )

    assert suggestions == []
    assert "OPENAI_API_KEY not set" in error


async def test_ollama_fails_fallback_budget_exceeded():
    with (
        patch(
            "prime_directive.core.dossier_ai.generate_ollama",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("ollama down"),
        ),
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.check_budget",
            new_callable=AsyncMock,
            return_value=(False, 15.0, 10.0),
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{
                    **_BASE_KWARGS,
                    "fallback_provider": "openai",
                    "db_path": "/tmp/test.db",
                }
            )
        )

    assert suggestions == []
    assert "Monthly budget exceeded" in error


async def test_ollama_fails_fallback_openai_also_fails():
    with (
        patch(
            "prime_directive.core.dossier_ai.generate_ollama",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("ollama down"),
        ),
        patch(
            "prime_directive.core.dossier_ai.get_openai_api_key",
            return_value="sk-test",
        ),
        patch(
            "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("openai also down"),
        ),
    ):
        suggestions, metadata, error = (
            await generate_theme_suggestions_with_ai(
                **{**_BASE_KWARGS, "fallback_provider": "openai"}
            )
        )

    assert suggestions == []
    assert "openai also down" in error


# ── _log_usage with db_path ──


async def test_log_usage_calls_log_ai_usage_when_db_path_set():
    with patch(
        "prime_directive.core.dossier_ai.log_ai_usage",
        new_callable=AsyncMock,
    ) as mock_log:
        await _log_usage(
            "/tmp/test.db", "openai", "gpt-4o-mini", 10, 5, 0.001, True
        )

    mock_log.assert_called_once_with(
        db_path="/tmp/test.db",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
        cost_estimate_usd=0.001,
        success=True,
        repo_id="dossier",
    )
