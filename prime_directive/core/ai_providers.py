import os
from typing import Optional
import time

import requests


def generate_ollama(
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
    Send a prompt to an Ollama-compatible API and return the model's generated content.
    
    Retries the request up to `max_retries` times (total attempts = max_retries + 1). When `backoff_seconds` > 0, waits with exponential backoff between retry attempts (sleep = backoff_seconds * 2**attempt).
    
    Parameters:
        api_url (str): Full URL of the Ollama-compatible endpoint to POST the request to.
        model (str): Model identifier to include in the request payload.
        prompt (str): User prompt text to send to the model.
        system (str): System/instructional prompt to include alongside the user prompt.
        timeout_seconds (float): Per-request timeout in seconds.
        max_retries (int): Number of retry attempts on failure (default 0).
        backoff_seconds (float): Base number of seconds to wait before retrying; used with exponential backoff (default 0.0).
    
    Returns:
        str: The model-generated content extracted from the response's "response" field.
    
    Raises:
        requests.exceptions.RequestException: If an HTTP/network error occurs on the final attempt.
        ValueError: If the response is missing or contains a non-empty string in the "response" field on the final attempt.
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
            response = requests.post(
                api_url,
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("response")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("No response field in Ollama payload")
            return content
        except (requests.exceptions.RequestException, ValueError) as e:
            last_error = e
            if attempt >= attempts - 1:
                break
            if backoff_seconds > 0:
                time.sleep(backoff_seconds * (2**attempt))

    assert last_error is not None
    raise last_error


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
    """
    Send a chat-style request to an OpenAI-compatible API and return the assistant's message content.
    
    Parameters:
        api_url (str): The API endpoint to POST the chat request to.
        api_key (str): Bearer token used for Authorization header.
        model (str): Model identifier to use for generation.
        system (str): System prompt providing high-level instructions or context.
        prompt (str): User prompt to send as the conversation's user message.
        timeout_seconds (float): Request timeout in seconds.
        max_tokens (int): Maximum number of tokens to generate for the response.
    
    Returns:
        str: The assistant message content with leading and trailing whitespace removed.
    
    Raises:
        ValueError: If the response is missing `choices`, the first choice lacks a `message` object, or the message `content` is empty or not a string.
    """
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

    response = requests.post(
        api_url,
        json=payload,
        headers=headers,
        timeout=timeout_seconds,
    )
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
    """
    Retrieve the OpenAI API key from the environment.
    
    Parameters:
        env_var (str): Name of the environment variable to read. Defaults to "OPENAI_API_KEY".
    
    Returns:
        The value of the environment variable if set, otherwise None.
    """
    return os.getenv(env_var) or None