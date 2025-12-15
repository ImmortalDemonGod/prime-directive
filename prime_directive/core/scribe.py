import requests
import time
from typing import Optional, Dict, Any

from prime_directive.core.ai_providers import generate_openai_chat, get_openai_api_key

def generate_sitrep(
    repo_id: str,
    git_state: str,
    terminal_logs: str,
    active_task: Optional[Dict[str, Any]] = None,
    model: str = "qwen2.5-coder",
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
    Generates a SITREP summary using Ollama.
    
    Args:
        repo_id (str): The ID of the repository.
        git_state (str): Summary of git status.
        terminal_logs (str): Recent terminal output.
        active_task (Optional[dict]): The current active task dictionary.
        model (str): The Ollama model to use.
        fallback_provider (str): The fallback provider to use if Ollama fails.
        fallback_model (str): The fallback model to use if Ollama fails.
        require_confirmation (bool): Whether to require confirmation for OpenAI fallback.
        openai_api_url (str): The OpenAI API endpoint.
        openai_timeout_seconds (float): The timeout in seconds for the OpenAI API request.
        openai_max_tokens (int): The maximum number of tokens for the OpenAI API request.
        api_url (str): The Ollama API endpoint.
        timeout_seconds (float): The timeout in seconds for the Ollama API request.
        max_retries (int): The maximum number of retries for the Ollama API request.
        backoff_seconds (float): The backoff time in seconds between retries.
        
    Returns:
        str: The generated SITREP string.
    """
    
    task_info = "None"
    if active_task:
        task_info = f"ID: {active_task.get('id')}\nTitle: {active_task.get('title')}\nDetails: {active_task.get('description')}"

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
        "generate a 2-3 sentence SITREP with IMMEDIATE NEXT STEP in 50 words max."
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False
    }

    last_error: Optional[Exception] = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            response = requests.post(api_url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "Error: No response from AI model.")
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt >= attempts - 1:
                break
            if backoff_seconds > 0:
                time.sleep(backoff_seconds * (2 ** attempt))

    if fallback_provider != "openai":
        return f"Error generating SITREP: {last_error!s}"

    if require_confirmation:
        return "Error generating SITREP: OpenAI fallback requires confirmation"

    api_key = get_openai_api_key()
    if not api_key:
        return "Error generating SITREP: OpenAI fallback requested but OPENAI_API_KEY not set"

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
    except requests.exceptions.RequestException as e:
        return f"Error generating SITREP: {e!s}"
