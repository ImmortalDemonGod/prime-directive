from typing import Optional, Dict, Any
import logging

import httpx

from prime_directive.core.ai_providers import (
    generate_ollama,
    generate_openai_chat,
    get_openai_api_key,
    log_ai_usage,
    check_budget,
    estimate_cost,
)

logger = logging.getLogger("prime_directive")


async def generate_sitrep(
    repo_id: str,
    git_state: str,
    terminal_logs: str,
    active_task: Optional[Dict[str, Any]] = None,
    human_objective: Optional[str] = None,
    human_blocker: Optional[str] = None,
    human_next_step: Optional[str] = None,
    human_note: Optional[str] = None,
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
    db_path: Optional[str] = None,
    monthly_budget_usd: float = 10.0,
    cost_per_1k_tokens: float = 0.002,
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
        require_confirmation (bool): Whether to require confirmation for OpenAI
            fallback.
        openai_api_url (str): The OpenAI API endpoint.
        openai_timeout_seconds (float): Timeout in seconds for the OpenAI
            request.
        openai_max_tokens (int): Maximum number of tokens for the OpenAI
            request.
        api_url (str): The Ollama API endpoint.
        timeout_seconds (float): Timeout in seconds for the Ollama request.
        max_retries (int): Maximum number of retries for the Ollama request.
        backoff_seconds (float): Backoff time in seconds between retries.

    Returns:
        str: The generated SITREP string.
    """

    task_info = "None"
    if active_task:
        task_info = (
            f"ID: {active_task.get('id')}\n"
            f"Title: {active_task.get('title')}\n"
            f"Details: {active_task.get('description')}"
        )

    human_info = "None"
    if human_objective or human_blocker or human_next_step or human_note:
        human_info = (
            f"Objective: {human_objective or 'None'}\n"
            f"Blocker: {human_blocker or 'None'}\n"
            f"Next Step: {human_next_step or 'None'}\n"
            f"Notes: {human_note or 'None'}"
        )

    prompt = f"""
    Context:
    - Repository: {repo_id}
    - Human Context:
    {human_info}
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

        # Budget check for paid provider
        if db_path:
            within_budget, current, budget = await check_budget(
                db_path,
                monthly_budget_usd,
            )
            if not within_budget:
                logger.warning(
                    f"Budget exceeded: ${current:.2f}/${budget:.2f}"
                )
                return (
                    "Error generating SITREP: Monthly budget exceeded "
                    f"(${current:.2f}/${budget:.2f})"
                )

        try:
            result = await generate_openai_chat(
                api_url=openai_api_url,
                api_key=api_key,
                model=model,
                system=system_prompt,
                prompt=prompt,
                timeout_seconds=openai_timeout_seconds,
                max_tokens=openai_max_tokens,
            )
            # Log usage (estimate tokens from response length)
            if db_path:
                output_tokens = len(result.split()) * 1.3  # rough estimate
                cost = estimate_cost(int(output_tokens), cost_per_1k_tokens)
                await log_ai_usage(
                    db_path=db_path,
                    provider="openai",
                    model=model,
                    input_tokens=0,  # not tracked
                    output_tokens=int(output_tokens),
                    cost_estimate_usd=cost,
                    success=True,
                    repo_id=repo_id,
                )
                logger.info(
                    "OpenAI call logged: "
                    f"~{int(output_tokens)} tokens, ${cost:.4f}"
                )
            return result
        except (httpx.HTTPError, ValueError) as e:
            if db_path:
                await log_ai_usage(
                    db_path=db_path,
                    provider="openai",
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    cost_estimate_usd=0.0,
                    success=False,
                    repo_id=repo_id,
                )
            return f"Error generating SITREP: {e!s}"

    # Default: Use Ollama as primary provider
    last_error: Optional[Exception] = None
    try:
        return await generate_ollama(
            api_url=api_url,
            model=model,
            prompt=prompt,
            system=system_prompt,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
        )
    except (httpx.HTTPError, ValueError) as e:
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

    # Budget check for fallback
    if db_path:
        within_budget, current, budget = await check_budget(
            db_path,
            monthly_budget_usd,
        )
        if not within_budget:
            logger.warning(
                "Budget exceeded for fallback: "
                f"${current:.2f}/${budget:.2f}"
            )
            return (
                "Error generating SITREP: Monthly budget exceeded "
                f"(${current:.2f}/${budget:.2f})"
            )

    try:
        result = await generate_openai_chat(
            api_url=openai_api_url,
            api_key=api_key,
            model=fallback_model,
            system=system_prompt,
            prompt=prompt,
            timeout_seconds=openai_timeout_seconds,
            max_tokens=openai_max_tokens,
        )
        # Log fallback usage
        if db_path:
            output_tokens = len(result.split()) * 1.3
            cost = estimate_cost(int(output_tokens), cost_per_1k_tokens)
            await log_ai_usage(
                db_path=db_path,
                provider="openai",
                model=fallback_model,
                input_tokens=0,
                output_tokens=int(output_tokens),
                cost_estimate_usd=cost,
                success=True,
                repo_id=repo_id,
            )
            logger.info(
                "OpenAI fallback logged: "
                f"~{int(output_tokens)} tokens, ${cost:.4f}"
            )
        return result
    except (httpx.HTTPError, ValueError) as e:
        if db_path:
            await log_ai_usage(
                db_path=db_path,
                provider="openai",
                model=fallback_model,
                input_tokens=0,
                output_tokens=0,
                cost_estimate_usd=0.0,
                success=False,
                repo_id=repo_id,
            )
        return f"Error generating SITREP: {e!s}"
