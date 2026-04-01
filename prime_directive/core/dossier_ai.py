from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from prime_directive.core.ai_providers import (
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
    payload = json.loads(_extract_json_text(raw_text))
    if isinstance(payload, dict):
        raw_suggestions = payload.get("suggestions", [])
    elif isinstance(payload, list):
        raw_suggestions = payload
    else:
        raise ValueError("Theme extraction response must be a JSON object or list")

    existing = {normalize_tag(tag) for tag in existing_tags if str(tag).strip()}
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
                occurrences=max(int(occurrences_raw), 0)
                if isinstance(occurrences_raw, int)
                else 0,
                sample=evidence,
                confidence=max(0.0, min(float(confidence_raw), 1.0))
                if isinstance(confidence_raw, (int, float))
                else 0.0,
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
    ) -> tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]:
        cost = estimate_cost(output_tokens, cost_per_1k_tokens) if used_provider == "openai" else 0.0
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
        usage: Optional[dict[str, int]],
    ) -> tuple[list[ThemeSuggestion], Optional[AIAnalysisMetadata], Optional[str]]:
        if usage is not None:
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
        else:
            input_tokens = _count_tokens(f"{system_prompt}\n{prompt}", used_model)
            output_tokens = _count_tokens(response_text, used_model)
        cost = estimate_cost(output_tokens, cost_per_1k_tokens) if used_provider == "openai" else 0.0
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
            return [], None, "Error generating theme suggestions: OPENAI_API_KEY not set"
        if db_path:
            within_budget, current, budget = await check_budget(db_path, monthly_budget_usd)
            if not within_budget:
                return [], None, (
                    "Error generating theme suggestions: Monthly budget exceeded "
                    f"(${current:.2f}/${budget:.2f})"
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
            return await finalize_success(response_text, "openai", model, usage)
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
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as primary_error:
        if fallback_provider != "openai":
            return await finalize_error("ollama", model, primary_error)

    if require_confirmation:
        return [], None, "Error generating theme suggestions: OpenAI fallback requires confirmation"

    api_key = get_openai_api_key()
    if not api_key:
        return [], None, (
            "Error generating theme suggestions: OpenAI fallback requested but OPENAI_API_KEY not set"
        )

    if db_path:
        within_budget, current, budget = await check_budget(db_path, monthly_budget_usd)
        if not within_budget:
            return [], None, (
                "Error generating theme suggestions: Monthly budget exceeded "
                f"(${current:.2f}/${budget:.2f})"
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
        return await finalize_success(response_text, "openai", fallback_model, usage)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
        return await finalize_error("openai", fallback_model, error)
