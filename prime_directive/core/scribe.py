from typing import Optional, Dict, Any
import logging

import httpx

from prime_directive.core.ai_providers import (
    generate_ollama,
    generate_openai_chat,
    generate_openai_chat_with_usage,
    get_openai_api_key,
    log_ai_usage,
    check_budget,
    estimate_cost,
)

logger = logging.getLogger("prime_directive")


def _count_tokens(text: str, model: str) -> int:
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        return len(enc.encode(text))
    except Exception:
        return 0


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
    Generate a concise SITREP (situation report) summarizing repository state, recent terminal output, and optional human/task context.
    
    Constructs a prompt from repo_id, git_state, terminal_logs, active_task, and human_* fields, then requests a short (2–3 sentence) SITREP with an immediate next step from the configured provider and model. By default uses Ollama; can use OpenAI as the primary provider or as a fallback. When OpenAI is used and db_path is provided, the function will check monthly budget and log estimated token usage and cost.
    
    Parameters:
        repo_id (str): Repository identifier included in the prompt.
        git_state (str): Concise summary of git state to include in the prompt.
        terminal_logs (str): Recent terminal output to include in the prompt.
        active_task (Optional[Dict[str, Any]]): Active task with keys like `id`, `title`, and `description`.
        human_objective (Optional[str]): Human-provided objective to include in the prompt.
        human_blocker (Optional[str]): Human-provided blocker to include in the prompt.
        human_next_step (Optional[str]): Human-provided suggested next step to include in the prompt.
        human_note (Optional[str]): Additional human notes to include in the prompt.
        model (str): Primary model name to request from the selected provider.
        provider (str): Primary provider to use; `"ollama"` or `"openai"`.
        fallback_provider (str): Provider to use if the primary provider fails; `"openai"` or `"none"`.
        fallback_model (str): Model name to use for the fallback provider.
        require_confirmation (bool): If true, prevents automatic OpenAI fallback and returns an error instead.
        openai_api_url (str): OpenAI API endpoint URL used when provider or fallback_provider is `"openai"`.
        openai_timeout_seconds (float): Request timeout for OpenAI calls.
        openai_max_tokens (int): Maximum tokens to request from OpenAI.
        api_url (str): Ollama API endpoint URL used when provider is `"ollama"`.
        timeout_seconds (float): Request timeout for Ollama calls.
        max_retries (int): Number of retries for Ollama requests.
        backoff_seconds (float): Backoff delay between Ollama retries.
        db_path (Optional[str]): Path to a local DB used for budget checks and logging; if None, budget checks and logging are skipped.
        monthly_budget_usd (float): Monthly budget threshold used when db_path is provided.
        cost_per_1k_tokens (float): Cost estimate per 1000 tokens used to compute estimated cost when logging usage.
    
    Returns:
        str: Generated SITREP text on success, or an error message beginning with "Error generating SITREP:" on failure.
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
        "You are a Chief of Staff for a senior engineer. "
        "Your job is to preserve and surface the human strategic context so the engineer can resume instantly. "
        "Prioritize (in this order): Human Objective, Human Blocker, Human Notes (Brain Dump), Human Next Step. "
        "Treat git state and terminal logs as supporting evidence only. "
        "Do not discard or compress away the Blocker or Notes; explicitly mention them. "
        "Write a compact SITREP that is decision- and next-action-oriented: "
        "(1) What we were trying to achieve, (2) what failed / key uncertainty, (3) what to do next. "
        "Keep it brief (<=120 words) and include an explicit NEXT STEP."
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
            result, usage = await generate_openai_chat_with_usage(
                api_url=openai_api_url,
                api_key=api_key,
                model=model,
                system=system_prompt,
                prompt=prompt,
                timeout_seconds=openai_timeout_seconds,
                max_tokens=openai_max_tokens,
            )
            # Log usage
            if db_path:
                if usage is not None:
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                else:
                    input_tokens = _count_tokens(
                        f"{system_prompt}\n{prompt}",
                        model,
                    )
                    output_tokens = _count_tokens(result, model)

                cost = estimate_cost(output_tokens, cost_per_1k_tokens)
                await log_ai_usage(
                    db_path=db_path,
                    provider="openai",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate_usd=cost,
                    success=True,
                    repo_id=repo_id,
                )
                logger.info(
                    "OpenAI call logged: "
                    f"{output_tokens} tokens, ${cost:.4f}"
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
        result, usage = await generate_openai_chat_with_usage(
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
            if usage is not None:
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
            else:
                input_tokens = _count_tokens(
                    f"{system_prompt}\n{prompt}",
                    fallback_model,
                )
                output_tokens = _count_tokens(result, fallback_model)

            cost = estimate_cost(output_tokens, cost_per_1k_tokens)
            await log_ai_usage(
                db_path=db_path,
                provider="openai",
                model=fallback_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_estimate_usd=cost,
                success=True,
                repo_id=repo_id,
            )
            logger.info(
                "OpenAI fallback logged: "
                f"{output_tokens} tokens, ${cost:.4f}"
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