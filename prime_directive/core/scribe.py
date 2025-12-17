import requests
from typing import Optional, Dict, Any

from prime_directive.core.ai_providers import (
    generate_ollama,
    generate_openai_chat,
    get_openai_api_key,
)


def generate_sitrep(
    repo_id: str,
    git_state: str,
    terminal_logs: str,
    active_task: Optional[Dict[str, Any]] = None,
    model: str = "qwen2.5-coder",
    provider: str = "ollama",
    fallback_provider: str = "none",
    fallback_model: str = "gpt-4o-mini",
    require_confirmation: bool = True,
    openai_api_url: str = "https://api.openai.com/v1/chat/completions",
    openai_timeout_seconds: float = 10.0,
    openai_max_tokens: int = 150,
    api_url: str = "http://localhost:11434/api/generate",
    timeout_seconds: float = 5.0,
    max_retries: int = 0,
    backoff_seconds: float = 0.0,
) -> str:
    """
    Generate a concise SITREP (situation report) from repository context.
    
    Parameters:
        repo_id (str): Repository identifier used in the prompt.
        git_state (str): Summary of the repository's git status.
        terminal_logs (str): Recent terminal output to include in the prompt.
        active_task (Optional[dict]): Current task information with optional keys
            'id', 'title', and 'description'. If omitted, task info is treated as None.
        provider (str): Primary provider to use; expected values include "ollama" or "openai".
        fallback_provider (str): Fallback provider to use if the primary provider fails;
            use "openai" to enable OpenAI fallback or "none" to disable fallback.
        require_confirmation (bool): If True, an OpenAI fallback is not attempted automatically
            and will return an error indicating confirmation is required.
        model (str): Primary model name to request from the selected provider.
        fallback_model (str): Model name to request when falling back to OpenAI.
        api_url (str): Ollama API endpoint.
        openai_api_url (str): OpenAI API endpoint.
        timeout_seconds (float): Timeout (seconds) for Ollama requests.
        openai_timeout_seconds (float): Timeout (seconds) for OpenAI requests.
        max_retries (int): Number of retries for Ollama requests.
        backoff_seconds (float): Backoff (seconds) between Ollama retries.
        openai_max_tokens (int): Max tokens to request from OpenAI.
    
    Returns:
        str: The generated SITREP text on success, or an error message describing why generation failed.
    """

    task_info = "None"
    if active_task:
        task_info = (
            f"ID: {active_task.get('id')}\n"
            f"Title: {active_task.get('title')}\n"
            f"Details: {active_task.get('description')}"
        )

    prompt = f"""
    Context:
    - Repository: {repo_id}
    - Active Task:
    {task_info}
    - Git State:
    {git_state}
    - Recent Terminal Logs:
    {terminal_logs}

    Generate a SITREP.
    """

    system_prompt = (
        "You are a concise engineering assistant. "
        "Given git state, terminal logs, and active task, "
        "generate a 2-3 sentence SITREP with IMMEDIATE NEXT STEP in "
        "50 words max."
    )

    # Use OpenAI as primary provider if configured
    if provider == "openai":
        api_key = get_openai_api_key()
        if not api_key:
            return "Error generating SITREP: OPENAI_API_KEY not set"
        try:
            return generate_openai_chat(
                api_url=openai_api_url,
                api_key=api_key,
                model=model,
                system=system_prompt,
                prompt=prompt,
                timeout_seconds=openai_timeout_seconds,
                max_tokens=openai_max_tokens,
            )
        except (requests.exceptions.RequestException, ValueError) as e:
            return f"Error generating SITREP: {e!s}"

    # Default: Use Ollama as primary provider
    last_error: Optional[Exception] = None
    try:
        return generate_ollama(
            api_url=api_url,
            model=model,
            prompt=prompt,
            system=system_prompt,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
        )
    except (requests.exceptions.RequestException, ValueError) as e:
        last_error = e

    if fallback_provider != "openai":
        if last_error is not None:
            message = str(last_error)
        else:
            message = "Unknown error contacting Ollama"
        return f"Error generating SITREP: {message}"

    if require_confirmation:
        return "Error generating SITREP: OpenAI fallback requires confirmation"

    api_key = get_openai_api_key()
    if not api_key:
        return (
            "Error generating SITREP: OpenAI fallback requested but "
            "OPENAI_API_KEY not set"
        )

    try:
        return generate_openai_chat(
            api_url=openai_api_url,
            api_key=api_key,
            model=fallback_model,
            system=system_prompt,
            prompt=prompt,
            timeout_seconds=openai_timeout_seconds,
            max_tokens=openai_max_tokens,
        )
    except (requests.exceptions.RequestException, ValueError) as e:
        return f"Error generating SITREP: {e!s}"