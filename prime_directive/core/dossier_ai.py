from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from prime_directive.core.ai_providers import (
    OpenAIUsage,
    check_budget,
    estimate_cost,
    generate_ollama,
    generate_openai_chat_with_usage,
    get_openai_api_key,
    log_ai_usage,
)
from prime_directive.core.identity import normalize_tag
from prime_directive.core.skill_scanner import ThemeSuggestion


@dataclass(frozen=True)
class AIAnalysisMetadata:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float


def _count_tokens(text: str, model: str) -> int:
    """
    Return the number of tokens in `text` according to the tokenizer for `model`.

    If the model-specific encoding is unavailable, falls back to the `cl100k_base` encoding. If the `tiktoken` package is not installed or any error occurs during encoding, returns `0` (a warning is logged when `tiktoken` is missing).

    Parameters:
        text (str): The input text to count tokens for.
        model (str): Model name used to select a tokenizer/encoding.

    Returns:
        int: The token count for `text`, or `0` if tokenization is unavailable or an error occurred.
    """
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        return len(enc.encode(text))
    except ImportError:
        import logging

        logging.getLogger("prime_directive").warning(
            "tiktoken not installed; token counts will be 0 and cost tracking inactive"
        )
        return 0
    except Exception:
        return 0


def _extract_json_text(raw_text: str) -> str:
    """
    Extract JSON content from text that may be wrapped in a fenced code block.

    If `raw_text` begins with a triple-backtick fenced block (``` or ```json), returns the trimmed contents of that block. Otherwise returns `raw_text` trimmed of leading and trailing whitespace.

    Parameters:
        raw_text (str): Text that may contain a fenced JSON code block.

    Returns:
        The inner text of the fenced code block if one is present, otherwise the trimmed input string.
    """
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
        if match:
            return match.group(1).strip()
    return stripped


def _parse_theme_suggestions_response(
    raw_text: str,
    existing_tags: list[str],
    limit: int,
) -> list[ThemeSuggestion]:
    """
    Parse and normalize theme suggestions from a JSON-formatted model response.

    Accepts either a JSON object containing a `suggestions` field or a top-level JSON list. Normalizes and deduplicates suggested tags against `existing_tags` and within the response, filters out blank or invalid tags, converts `occurrences` to a non-negative integer, clamps `confidence` to the range 0.0–1.0, and returns up to `limit` ThemeSuggestion instances preserving the order they appeared.

    Parameters:
        raw_text (str): Raw text returned by the model; may contain fenced code blocks and/or plain JSON.
        existing_tags (list[str]): Tags to exclude from the results; each tag will be normalized before comparison.
        limit (int): Maximum number of suggestions to return.

    Returns:
        list[ThemeSuggestion]: A list of normalized, deduplicated theme suggestions (at most `limit` items).

    Raises:
        ValueError: If the parsed JSON is neither an object nor a list.
    """
    payload = json.loads(_extract_json_text(raw_text))
    if isinstance(payload, dict):
        raw_suggestions = payload.get("suggestions", [])
    elif isinstance(payload, list):
        raw_suggestions = payload
    else:
        raise ValueError(
            "Theme extraction response must be a JSON object or list"
        )

    existing = {
        normalize_tag(tag) for tag in existing_tags if str(tag).strip()
    }
    suggestions: list[ThemeSuggestion] = []
    seen: set[str] = set()

    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue
        normalized = normalize_tag(str(item.get("tag", "")))
        if not normalized or normalized in existing or normalized in seen:
            continue
        occurrences_raw = item.get("occurrences", 0)
        confidence_raw = item.get("confidence", 0.0)
        evidence = str(item.get("evidence", "")).strip()
        suggestions.append(
            ThemeSuggestion(
                tag=normalized,
                occurrences=(
                    max(int(occurrences_raw), 0)
                    if isinstance(occurrences_raw, int)
                    else 0
                ),
                sample=evidence,
                confidence=(
                    max(0.0, min(float(confidence_raw), 1.0))
                    if isinstance(confidence_raw, (int, float))
                    else 0.0
                ),
            )
        )
        seen.add(normalized)

    return suggestions[:limit]


async def _log_usage(
    db_path: Optional[str],
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_estimate_usd: float,
    success: bool,
) -> None:
    """
    Record AI usage metrics to persistent storage when a database path is provided.

    If `db_path` is falsy the function returns immediately and no data is recorded.

    Parameters:
        db_path (Optional[str]): Path to the usage database; if falsy, logging is skipped.
        provider (str): Name of the AI provider (e.g., "openai", "ollama").
        model (str): Model identifier used for the request.
        input_tokens (int): Number of input tokens counted for the request.
        output_tokens (int): Number of output tokens produced by the request.
        cost_estimate_usd (float): Estimated cost in USD associated with the response.
        success (bool): Whether the AI request completed successfully.
    """
    if not db_path:
        return
    await log_ai_usage(
        db_path=db_path,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate_usd=cost_estimate_usd,
        success=success,
        repo_id="dossier",
    )


async def generate_theme_suggestions_with_ai(
    *,
    snapshot_texts: list[str],
    existing_tags: list[str],
    model: str,
    provider: str,
    fallback_provider: str,
    fallback_model: str,
    require_confirmation: bool,
    openai_api_url: str,
    openai_timeout_seconds: float,
    openai_max_tokens: int,
    api_url: str,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
    db_path: Optional[str],
    monthly_budget_usd: float,
    cost_per_1k_tokens: float,
    limit: int = 5,
    max_prompt_chars: int = 12000,
) -> tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]:
    """
    Generate a list of recurring technical theme suggestions from provided snapshot texts using an AI provider.

    Builds a prompt from the given snapshot texts and requests strict JSON theme suggestions from the selected provider (OpenAI or Ollama), optionally falling back to OpenAI. Results are normalized, deduplicated against existing tags, clamped to the requested limit, and accompanied by usage metadata when available. Errors produce a user-visible message instead of suggestions.

    Parameters:
        snapshot_texts (list[str]): Ordered pieces of recent context to analyze; blank items are ignored.
        existing_tags (list[str]): Tags to exclude from suggestions (case/format normalization applied).
        model (str): Primary model to request from the chosen provider.
        provider (str): Primary provider identifier (e.g., "openai", "ollama").
        fallback_provider (str): Provider to use if the primary provider fails.
        fallback_model (str): Model to use with the fallback provider.
        require_confirmation (bool): If True, require explicit confirmation before using the OpenAI fallback.
        openai_api_url (str): Base URL for OpenAI API requests.
        openai_timeout_seconds (float): Request timeout for OpenAI calls.
        openai_max_tokens (int): Maximum tokens to request from OpenAI for the response.
        api_url (str): Base URL for the primary provider (e.g., Ollama).
        timeout_seconds (float): Request timeout for the primary provider.
        max_retries (int): Number of retries for the primary provider.
        backoff_seconds (float): Backoff delay between retries for the primary provider.
        db_path (Optional[str]): If provided, usage and budget checks are persisted to this database.
        monthly_budget_usd (float): Monthly budget used to determine whether to permit OpenAI requests.
        cost_per_1k_tokens (float): Cost per 1k output tokens used to estimate OpenAI cost.
        limit (int): Maximum number of theme suggestions to return (default 5).
        max_prompt_chars (int): Maximum combined character length of snapshots included in the prompt (default 12000).

    Returns:
        tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]:
            A tuple containing:
            - A list of parsed ThemeSuggestion objects (may be empty on error or no data),
            - AIAnalysisMetadata with provider, model, token counts, and estimated cost when available, otherwise None,
            - An error message string when generation failed, otherwise None.
    """
    joined_snapshots = "\n\n".join(
        f"[{index}] {text.strip()}"
        for index, text in enumerate(snapshot_texts, start=1)
        if text and text.strip()
    )
    if not joined_snapshots:
        return [], None, None
    if len(joined_snapshots) > max_prompt_chars:
        joined_snapshots = joined_snapshots[:max_prompt_chars]

    prompt = (
        "Recent context snapshots:\n"
        f"{joined_snapshots}\n\n"
        "Extract up to 5 recurring technical themes suitable for capabilities.domain_expertise. "
        "Only include themes supported by multiple snapshots. Exclude philosophy, personality, and vague terms. "
        "Do not repeat any of these existing tags: "
        f"{', '.join(existing_tags) or 'none'}. "
        "Return strict JSON with this schema: "
        '{"suggestions":[{"tag":"lowercase-hyphenated-tag","occurrences":3,"evidence":"brief evidence string","confidence":0.7}]}'
    )
    system_prompt = (
        "You extract recurring technical themes from engineering work logs. "
        "Return only valid JSON. Tags must be lowercase, hyphenated, and specific enough for operator identity matching."
    )

    async def finalize_error(
        used_provider: str,
        used_model: str,
        error: Exception,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> tuple[
        list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]
    ]:
        """
        Finalize an error path by recording AI usage and returning a standardized error result.

        Records usage metrics (including a cost estimate when `used_provider` is "openai") and returns an empty suggestions list, no metadata, and a user-facing error message.

        Parameters:
            used_provider (str): The AI provider identifier used for the attempt.
            used_model (str): The model name used for the attempt.
            error (Exception): The exception that occurred; its string form is included in the returned message.
            input_tokens (int): Number of input tokens to record (default 0).
            output_tokens (int): Number of output tokens to record (default 0).

        Returns:
            tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]:
                An empty list of suggestions, `None` metadata, and an error message string prefixed with
                "Error generating theme suggestions: ".
        """
        cost = (
            estimate_cost(output_tokens, cost_per_1k_tokens)
            if used_provider == "openai"
            else 0.0
        )
        await _log_usage(
            db_path,
            used_provider,
            used_model,
            input_tokens,
            output_tokens,
            cost,
            False,
        )
        return [], None, f"Error generating theme suggestions: {error!s}"

    async def finalize_success(
        response_text: str,
        used_provider: str,
        used_model: str,
        usage: Optional[OpenAIUsage],
    ) -> tuple[
        list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]
    ]:
        """
        Finalize a successful AI response by parsing theme suggestions, recording usage, and producing analysis metadata.

        Parameters:
            response_text (str): Raw text returned by the AI provider.
            used_provider (str): Identifier of the provider that produced the response (e.g., "openai", "ollama").
            used_model (str): Model name used to generate the response.
            usage (Optional[OpenAIUsage]): Optional OpenAI usage metadata containing token counts (e.g., `{"prompt_tokens": int, "completion_tokens": int}`); if omitted, token counts are estimated from the prompt and response.

        Returns:
            tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]:
                - A list of parsed `ThemeSuggestion` objects (may be empty).
                - An `AIAnalysisMetadata` instance with provider, model, input/output token counts, and an estimated cost when available, or `None` if parsing failed.
                - An error message `str` when parsing or processing failed, or `None` on success.
        """
        if usage is not None:
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
        else:
            input_tokens = _count_tokens(
                f"{system_prompt}\n{prompt}", used_model
            )
            output_tokens = _count_tokens(response_text, used_model)
        cost = (
            estimate_cost(output_tokens, cost_per_1k_tokens)
            if used_provider == "openai"
            else 0.0
        )
        try:
            suggestions = _parse_theme_suggestions_response(
                response_text,
                existing_tags,
                limit,
            )
        except (ValueError, json.JSONDecodeError) as parse_error:
            return await finalize_error(
                used_provider,
                used_model,
                parse_error,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        await _log_usage(
            db_path,
            used_provider,
            used_model,
            input_tokens,
            output_tokens,
            cost,
            True,
        )
        return (
            suggestions,
            AIAnalysisMetadata(
                provider=used_provider,
                model=used_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_estimate_usd=cost,
            ),
            None,
        )

    if provider == "openai":
        api_key = get_openai_api_key()
        if not api_key:
            return (
                [],
                None,
                "Error generating theme suggestions: OPENAI_API_KEY not set",
            )
        if db_path:
            within_budget, current, budget = await check_budget(
                db_path, monthly_budget_usd
            )
            if not within_budget:
                return (
                    [],
                    None,
                    (
                        "Error generating theme suggestions: Monthly budget exceeded "
                        f"(${current:.2f}/${budget:.2f})"
                    ),
                )
        try:
            response_text, usage = await generate_openai_chat_with_usage(
                api_url=openai_api_url,
                api_key=api_key,
                model=model,
                system=system_prompt,
                prompt=prompt,
                timeout_seconds=openai_timeout_seconds,
                max_tokens=openai_max_tokens,
            )
            return await finalize_success(
                response_text, "openai", model, usage
            )
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            return await finalize_error("openai", model, error)

    try:
        response_text = await generate_ollama(
            api_url=api_url,
            model=model,
            prompt=prompt,
            system=system_prompt,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
        )
        return await finalize_success(response_text, "ollama", model, None)
    except (
        httpx.HTTPError,
        ValueError,
        json.JSONDecodeError,
    ) as primary_error:
        if fallback_provider != "openai":
            return await finalize_error("ollama", model, primary_error)

    if require_confirmation:
        return (
            [],
            None,
            "Error generating theme suggestions: OpenAI fallback requires confirmation",
        )

    api_key = get_openai_api_key()
    if not api_key:
        return (
            [],
            None,
            (
                "Error generating theme suggestions: OpenAI fallback requested but OPENAI_API_KEY not set"
            ),
        )

    if db_path:
        within_budget, current, budget = await check_budget(
            db_path, monthly_budget_usd
        )
        if not within_budget:
            return (
                [],
                None,
                (
                    "Error generating theme suggestions: Monthly budget exceeded "
                    f"(${current:.2f}/${budget:.2f})"
                ),
            )

    try:
        response_text, usage = await generate_openai_chat_with_usage(
            api_url=openai_api_url,
            api_key=api_key,
            model=fallback_model,
            system=system_prompt,
            prompt=prompt,
            timeout_seconds=openai_timeout_seconds,
            max_tokens=openai_max_tokens,
        )
        return await finalize_success(
            response_text, "openai", fallback_model, usage
        )
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
        return await finalize_error("openai", fallback_model, error)
