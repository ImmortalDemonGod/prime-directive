import os
from typing import Optional

import requests


def generate_ollama(
    *,
    api_url: str,
    model: str,
    prompt: str,
    system: str,
    timeout_seconds: float,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }

    response = requests.post(api_url, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "Error: No response from AI model.")


def generate_openai_chat(
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

    response = requests.post(api_url, json=payload, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices")
    if not choices:
        return "Error: No response from AI model."

    message = choices[0].get("message")
    if not isinstance(message, dict):
        return "Error: No response from AI model."

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return "Error: No response from AI model."

    return content.strip()


def get_openai_api_key(env_var: str = "OPENAI_API_KEY") -> Optional[str]:
    return os.getenv(env_var) or None
