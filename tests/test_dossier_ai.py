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
