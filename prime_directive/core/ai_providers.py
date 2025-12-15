import asyncio
import os
from typing import Optional

import httpx


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
