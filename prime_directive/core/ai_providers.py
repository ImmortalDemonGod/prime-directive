import asyncio
import os
from datetime import datetime, timezone
from typing import Optional, Tuple, TypedDict

import httpx
from sqlalchemy import select, func


async def log_ai_usage(
    db_path: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_estimate_usd: float,
    success: bool,
    repo_id: Optional[str] = None,
) -> None:
    """
    Persist an AI usage record to the database for tracking and budget enforcement.
    
    Parameters:
    	db_path (str): Filesystem path or connection string for the database to initialize and use.
    	provider (str): Name of the AI provider (e.g., "openai", "ollama").
    	model (str): Model identifier used for the request.
    	input_tokens (int): Number of tokens sent as input.
    	output_tokens (int): Number of tokens received as output.
    	cost_estimate_usd (float): Estimated cost for this call in US dollars.
    	success (bool): Whether the request completed successfully.
    	repo_id (Optional[str]): Optional repository identifier associated with the usage record.
    """
    from prime_directive.core.db import AIUsageLog, init_db, get_session

    await init_db(db_path)
    async for session in get_session(db_path):
        usage = AIUsageLog(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost_estimate_usd,
            success=success,
            repo_id=repo_id,
        )
        session.add(usage)
        await session.commit()
        break


async def get_monthly_usage(db_path: str) -> Tuple[float, int]:
    """
    Compute the total estimated cost and number of calls for the paid provider "openai" since the start of the current month (UTC).
    
    Returns:
        (total_cost_usd, call_count): total estimated cost in USD as a float and the number of recorded calls as an int for provider "openai" from the beginning of the current month (UTC).
    """
    from prime_directive.core.db import AIUsageLog, init_db, get_session
    from typing import cast, Any

    await init_db(db_path)

    # Get first day of current month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async for session in get_session(db_path):
        ts_col = cast(Any, AIUsageLog.timestamp)
        provider_col = cast(Any, AIUsageLog.provider)
        cost_col = cast(Any, AIUsageLog.cost_estimate_usd)

        stmt = (
            select(
                func.coalesce(func.sum(cost_col), 0.0),
                func.count(1),
            )
            .where(ts_col >= month_start)
            .where(provider_col == "openai")  # Only track paid provider
        )
        result = await session.execute(stmt)
        row = result.one()
        return float(row[0]), int(row[1])

    return 0.0, 0


async def check_budget(
    db_path: str,
    monthly_budget_usd: float,
) -> Tuple[bool, float, float]:
    """
    Determine whether the current month's AI usage is below a specified USD budget.
    
    Parameters:
        db_path (str): Filesystem path to the database containing AI usage logs.
        monthly_budget_usd (float): Budget in US dollars to compare against current month usage.
    
    Returns:
        Tuple[bool, float, float]: A tuple containing:
            - `true` if the current month's usage is less than `monthly_budget_usd`, `false` otherwise.
            - The current month's total estimated cost in USD.
            - The supplied `monthly_budget_usd` value.
    """
    current_usage, _ = await get_monthly_usage(db_path)
    return (
        current_usage < monthly_budget_usd,
        current_usage,
        monthly_budget_usd,
    )


def estimate_cost(output_tokens: int, cost_per_1k: float = 0.002) -> float:
    """
    Estimate cost from output token count using a per-1k-token rate.
    
    Parameters:
        output_tokens (int): Number of output tokens to price.
        cost_per_1k (float): Cost in USD per 1000 tokens (default 0.002).
    
    Returns:
        float: Estimated cost in USD.
    """
    return (output_tokens / 1000) * cost_per_1k


async def generate_ollama(
    *,
    api_url: str,
    model: str,
    prompt: str,
    system: str,
    timeout_seconds: float,
    max_retries: int = 0,
    backoff_seconds: float = 0.0,
) -> str:
    """
    Request a completion from an Ollama HTTP API and return the generated text.
    
    Parameters:
        api_url (str): Full Ollama endpoint URL to POST the request to.
        model (str): Model identifier to use for generation.
        prompt (str): User prompt to send to the model.
        system (str): System/instructional context to include with the prompt.
        timeout_seconds (float): Request timeout in seconds for each attempt.
        max_retries (int): Number of retry attempts to perform on failure (default 0).
        backoff_seconds (float): Base backoff seconds for exponential backoff between retries (default 0.0).
    
    Returns:
        str: The generated response text from the Ollama API.
    
    Raises:
        httpx.HTTPError: If the HTTP request fails and all retry attempts are exhausted.
        ValueError: If the response payload is missing a valid `response` string.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }

    last_error: Optional[Exception] = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(api_url, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("response")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("No response field in Ollama payload")
            return content
        except (httpx.HTTPError, ValueError) as e:
            last_error = e
            if attempt >= attempts - 1:
                break
            if backoff_seconds > 0:
                await asyncio.sleep(backoff_seconds * (2**attempt))

    assert last_error is not None
    raise last_error


async def generate_openai_chat(
    *,
    api_url: str,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> str:
    """
    Send a chat-style request to an OpenAI-compatible API and return the assistant's reply.
    
    Parameters:
        api_url (str): Full URL of the OpenAI-compatible chat completions endpoint.
        api_key (str): Bearer API key used for Authorization.
        model (str): Model identifier to request (e.g., "gpt-4").
        system (str): System prompt controlling assistant behavior.
        prompt (str): User prompt content.
        timeout_seconds (float): Request timeout in seconds.
        max_tokens (int): Maximum number of tokens to generate for the assistant.
    
    Returns:
        str: The assistant's response content with surrounding whitespace removed.
    
    Raises:
        ValueError: If the response JSON is missing choices, message, or content.
        httpx.HTTPError: If the HTTP request failed or returned a non-success status.
    """
    content, _usage = await generate_openai_chat_with_usage(
        api_url=api_url,
        api_key=api_key,
        model=model,
        system=system,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )
    return content


class OpenAIUsage(TypedDict, total=False):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


async def generate_openai_chat_with_usage(
    *,
    api_url: str,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> Tuple[str, Optional[OpenAIUsage]]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(api_url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices")
    if not choices:
        raise ValueError("No choices in AI response")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("No message object in AI response")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("No content in AI response")

    usage_raw = data.get("usage")
    usage: Optional[OpenAIUsage] = None
    if isinstance(usage_raw, dict):
        prompt_tokens = usage_raw.get("prompt_tokens")
        completion_tokens = usage_raw.get("completion_tokens")
        total_tokens = usage_raw.get("total_tokens")

        parsed: OpenAIUsage = {}
        if isinstance(prompt_tokens, int):
            parsed["prompt_tokens"] = prompt_tokens
        if isinstance(completion_tokens, int):
            parsed["completion_tokens"] = completion_tokens
        if isinstance(total_tokens, int):
            parsed["total_tokens"] = total_tokens

        if parsed:
            usage = parsed

    return content.strip(), usage


def get_openai_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    return os.getenv(env_var) or None