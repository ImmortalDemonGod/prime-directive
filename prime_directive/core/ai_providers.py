import asyncio
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

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
    """Log AI usage to the database for tracking and budget enforcement."""
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
    """Get current month's total cost and call count for paid providers."""
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
                func.count(AIUsageLog.id),
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
    """Check if within budget. Returns (within_budget, current_usage, budget)."""
    current_usage, _ = await get_monthly_usage(db_path)
    return (
        current_usage < monthly_budget_usd,
        current_usage,
        monthly_budget_usd,
    )


def estimate_cost(output_tokens: int, cost_per_1k: float = 0.002) -> float:
    """Estimate cost based on output tokens."""
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

    return content.strip()


def get_openai_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    return os.getenv(env_var) or None
