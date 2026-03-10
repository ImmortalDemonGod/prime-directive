from unittest.mock import AsyncMock, patch

from prime_directive.core.dossier_ai import generate_theme_suggestions_with_ai


async def test_generate_theme_suggestions_with_ai_openai_success():
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
        new_callable=AsyncMock,
        return_value=(
            '{"suggestions":[{"tag":"gradient-debugging","occurrences":3,"evidence":"3 snapshots mention gradient debugging","confidence":0.7}]}',
            {"prompt_tokens": 12, "completion_tokens": 8},
        ),
    ):
        suggestions, metadata, error = await generate_theme_suggestions_with_ai(
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

    assert error is None
    assert [item.tag for item in suggestions] == ["gradient-debugging"]
    assert metadata is not None
    assert metadata.provider == "openai"
    assert metadata.input_tokens == 12
    assert metadata.output_tokens == 8


async def test_generate_theme_suggestions_with_ai_blocks_when_budget_exceeded():
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.check_budget",
        new_callable=AsyncMock,
        return_value=(False, 12.0, 10.0),
    ):
        suggestions, metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["Investigating gradient debugging for diffusion training instability."],
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

    assert suggestions == []
    assert metadata is None
    assert error is not None
    assert "Monthly budget exceeded" in error


async def test_generate_theme_suggestions_with_ai_empty_snapshots_returns_empty():
    """Test that empty snapshot texts return empty suggestions."""
    suggestions, metadata, error = await generate_theme_suggestions_with_ai(
        snapshot_texts=[],
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

    assert suggestions == []
    assert metadata is None
    assert error is None


async def test_generate_theme_suggestions_with_ai_filters_existing_tags():
    """Test that suggestions exclude already-existing tags."""
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
        new_callable=AsyncMock,
        return_value=(
            '{"suggestions":[{"tag":"gradient-debugging","occurrences":3,"evidence":"test","confidence":0.7},{"tag":"existing-tag","occurrences":5,"evidence":"test2","confidence":0.8}]}',
            {"prompt_tokens": 12, "completion_tokens": 8},
        ),
    ):
        suggestions, _metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["test"],
            existing_tags=["existing-tag"],
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

    assert error is None
    assert len(suggestions) == 1
    assert suggestions[0].tag == "gradient-debugging"


async def test_generate_theme_suggestions_with_ai_ollama_fallback_to_openai():
    """Test that Ollama failure falls back to OpenAI."""
    import httpx

    req = httpx.Request("POST", "http://localhost:11434/api/generate")
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused", request=req),
    ), patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
        new_callable=AsyncMock,
        return_value=(
            '{"suggestions":[{"tag":"test-tag","occurrences":2,"evidence":"test","confidence":0.6}]}',
            {"prompt_tokens": 10, "completion_tokens": 5},
        ),
    ):
        suggestions, metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["test"],
            existing_tags=[],
            model="qwen2.5-coder",
            provider="ollama",
            fallback_provider="openai",
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

    assert error is None
    assert len(suggestions) == 1
    assert metadata.provider == "openai"


async def test_generate_theme_suggestions_with_ai_requires_confirmation_blocks_fallback():
    """Test that require_confirmation blocks OpenAI fallback."""
    import httpx

    req = httpx.Request("POST", "http://localhost:11434/api/generate")
    with patch(
        "prime_directive.core.dossier_ai.generate_ollama",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused", request=req),
    ), patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ):
        suggestions, metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["test"],
            existing_tags=[],
            model="qwen2.5-coder",
            provider="ollama",
            fallback_provider="openai",
            fallback_model="gpt-4o-mini",
            require_confirmation=True,
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

    assert suggestions == []
    assert metadata is None
    assert error is not None
    assert "requires confirmation" in error


async def test_generate_theme_suggestions_with_ai_handles_malformed_json():
    """Test that malformed JSON response is handled gracefully."""
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
        new_callable=AsyncMock,
        return_value=(
            "not valid json at all",
            {"prompt_tokens": 10, "completion_tokens": 5},
        ),
    ):
        suggestions, metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["test"],
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

    assert suggestions == []
    assert metadata is None
    assert error is not None


async def test_generate_theme_suggestions_with_ai_normalizes_tag_case():
    """Test that returned tags are normalized to lowercase-hyphenated format."""
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
        new_callable=AsyncMock,
        return_value=(
            '{"suggestions":[{"tag":"Gradient Debugging","occurrences":3,"evidence":"test","confidence":0.7}]}',
            {"prompt_tokens": 12, "completion_tokens": 8},
        ),
    ):
        suggestions, _metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["test"],
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

    assert error is None
    assert suggestions[0].tag == "gradient-debugging"


async def test_generate_theme_suggestions_with_ai_respects_limit():
    """Test that suggestions are limited to the specified count."""
    with patch(
        "prime_directive.core.dossier_ai.get_openai_api_key",
        return_value="sk-test",
    ), patch(
        "prime_directive.core.dossier_ai.generate_openai_chat_with_usage",
        new_callable=AsyncMock,
        return_value=(
            '{"suggestions":[{"tag":"tag1","occurrences":3,"evidence":"test","confidence":0.7},{"tag":"tag2","occurrences":3,"evidence":"test","confidence":0.7},{"tag":"tag3","occurrences":3,"evidence":"test","confidence":0.7},{"tag":"tag4","occurrences":3,"evidence":"test","confidence":0.7}]}',
            {"prompt_tokens": 12, "completion_tokens": 8},
        ),
    ):
        suggestions, _metadata, error = await generate_theme_suggestions_with_ai(
            snapshot_texts=["test"],
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
            limit=2,
        )

    assert error is None
    assert len(suggestions) == 2