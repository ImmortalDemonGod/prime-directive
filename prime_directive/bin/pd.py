import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import sys
import difflib
from typing import Any, Optional, cast

from dotenv import load_dotenv
import httpx
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
import typer

# Hydra imports
from hydra import compose, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig

# Core imports
from prime_directive.core.config import register_configs
from prime_directive.core.git_utils import GitStatus, get_status
from prime_directive.core.db import (
    ContextSnapshot,
    EventLog,
    EventType,
    dispose_engine,
    get_session,
    init_db,
)
from prime_directive.core.terminal import capture_terminal_state
from prime_directive.core.tasks import get_active_task
from prime_directive.core.scribe import generate_sitrep
from prime_directive.core.tmux import ensure_session
from prime_directive.core.windsurf import launch_editor
from prime_directive.core.logging_utils import setup_logging
from prime_directive.core.orchestrator import run_switch
from prime_directive.core.dependencies import (
    get_ollama_status,
    has_openai_api_key,
)

# Load .env from multiple locations (in order of priority)
# 1. Current working directory
# 2. User's home ~/.prime-directive/.env
# 3. The prime-directive repo root
load_dotenv()  # CWD
load_dotenv(Path.home() / ".prime-directive" / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")

app = typer.Typer()
# Export cli for entry point
cli = app
console = Console()
logger = logging.getLogger("prime_directive")

_EXIT_CODE_SHELL_ATTACH = 88


def _normalize_repo_id(repo_id: str) -> str:
    return repo_id.strip().rstrip("/\\")


def _resolve_repo_id(repo_id: str, cfg: DictConfig) -> str:
    candidate = _normalize_repo_id(repo_id)
    if candidate in cfg.repos:
        return candidate

    matches = difflib.get_close_matches(
        candidate,
        list(cfg.repos.keys()),
        n=1,
        cutoff=0.6,
    )
    msg = f"Repository '{repo_id}' not found in configuration."
    if matches:
        msg = f"{msg} Did you mean '{matches[0]}'?"
    console.print(f"[bold red]Error:[/bold red] {msg}")
    logger.error(msg)
    raise typer.Exit(code=1)


def load_config() -> DictConfig:
    """
    Load and compose the application's Hydra configuration.
    
    Composes and returns the structured `DictConfig` for the application. If configuration loading fails, prints an error, logs it, and exits the process with status code 1.
    
    Returns:
        DictConfig: The composed Hydra configuration for the application.
    """
    # Ensure any previous Hydra instance is cleared
    GlobalHydra.instance().clear()

    # Register structured configs
    register_configs()

    # Compute absolute path to conf directory relative to this file
    # pd.py is in prime_directive/bin/, conf is in prime_directive/conf/
    conf_dir = Path(__file__).parent.parent / "conf"
    conf_path = str(conf_dir.resolve())

    try:
        with initialize_config_dir(version_base=None, config_dir=conf_path):
            cfg = compose(config_name="config")
            return cfg
    except Exception as e:
        msg = f"Error loading config: {e}"
        console.print(f"[bold red]{msg}[/bold red]")
        logger.critical(msg)
        sys.exit(1)


# Initialize logging globally with default, will be re-configured if needed
setup_logging()


async def freeze_logic(
    repo_id: str,
    config: DictConfig,
    human_note: Optional[str] = None,
    human_objective: Optional[str] = None,
    human_blocker: Optional[str] = None,
    human_next_step: Optional[str] = None,
    skip_terminal_capture: bool = False,
    use_hq_model: bool = False,
):
    """
    Freeze the current repository context, generate an AI SITREP, and persist a ContextSnapshot to the database.
    
    Captures repository git state, terminal state (unless skipped), and active task; generates an AI SITREP using configured AI provider/model (optionally using the HQ model), and saves a ContextSnapshot (creating the Repository record if missing). Prints summary output to the console.
    
    Parameters:
    	repo_id (str): Identifier of the repository to freeze as defined in `config.repos`.
    	config (DictConfig): Composed Hydra configuration object with system and repo settings.
    	human_note (Optional[str]): Optional free-form note to attach to the snapshot.
    	human_objective (Optional[str]): Optional human-provided objective to include in the SITREP and snapshot.
    	human_blocker (Optional[str]): Optional human-provided blocker to include in the SITREP and snapshot.
    	human_next_step (Optional[str]): Optional human-provided next step to include in the SITREP and snapshot.
    	skip_terminal_capture (bool): If True, do not attempt to capture terminal state and store placeholder values.
    	use_hq_model (bool): If True, prefer the configured high-quality model/provider for SITREP generation.
    
    Raises:
    	ValueError: If `repo_id` is not present in `config.repos`.
    """
    candidate = _normalize_repo_id(repo_id)
    if candidate not in config.repos:
        matches = difflib.get_close_matches(
            candidate,
            list(config.repos.keys()),
            n=1,
            cutoff=0.6,
        )
        msg = f"Repository '{repo_id}' not found in configuration."
        if matches:
            msg = f"{msg} Did you mean '{matches[0]}'?"
        console.print(f"[bold red]Error:[/bold red] {msg}")
        logger.error(msg)
        raise ValueError(msg)

    repo_id = candidate
    repo_config = config.repos[repo_id]
    repo_path = repo_config.path

    logger.info(f"Freezing context for {repo_id} at {repo_path}")
    console.print(f"[bold blue]Freezing context for {repo_id}...[/bold blue]")

    # 1. Capture Git State (Sync/Blocking)
    # 2. Capture Terminal State (Sync/Blocking)
    # These operations are independent and can be executed concurrently.
    git_st: GitStatus
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping actual git status check")
        git_summary = "MOCK: Branch: main\nDirty: False"
        git_st = {
            "branch": "main",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": "",
        }

        logger.info("MOCK MODE: Skipping terminal capture")
        last_cmd = "mock_cmd"
        term_output = "MOCK: Terminal output"
    elif skip_terminal_capture:
        git_st = await get_status(repo_path)
        git_summary = (
            f"Branch: {git_st['branch']}\n"
            f"Dirty: {git_st['is_dirty']}\n"
            f"Files: {git_st['uncommitted_files']}\n"
            f"Diff: {git_st.get('diff_stat', '')}"
        )

        last_cmd = "unknown"
        term_output = "Terminal capture skipped."
    else:
        git_task = asyncio.create_task(get_status(repo_path))
        term_task = asyncio.create_task(capture_terminal_state(repo_id))

        try:
            git_result, term_result = await asyncio.gather(
                git_task,
                term_task,
                return_exceptions=True,
            )
        except Exception as e:
            logger.exception(
                "Error running concurrent freeze capture steps",
                extra={"repo_id": repo_id},
            )
            git_result = e
            term_result = e

        if isinstance(git_result, BaseException):
            logger.warning(
                f"Git state capture failed for {repo_id}: {git_result!s}"
            )
            git_st = {
                "branch": "error",
                "is_dirty": False,
                "uncommitted_files": [],
                "diff_stat": str(git_result),
            }
        else:
            git_st = git_result

        git_summary = (
            f"Branch: {git_st['branch']}\n"
            f"Dirty: {git_st['is_dirty']}\n"
            f"Files: {git_st['uncommitted_files']}\n"
            f"Diff: {git_st.get('diff_stat', '')}"
        )

        if isinstance(term_result, BaseException):
            logger.warning(
                f"Terminal capture failed for {repo_id}: {term_result!s}"
            )
            last_cmd = "unknown"
            term_output = "Unexpected error during terminal capture."
        else:
            last_cmd, term_output = term_result

    logger.debug(f"Git state for {repo_id}: {git_st}")
    logger.debug(f"Terminal state: cmd={last_cmd}")

    # 3. Capture Active Task (Sync)
    active_task = get_active_task(repo_path)
    logger.debug(f"Active task: {active_task}")

    # 4. Generate AI SITREP (Blocking Network Call - could be made async
    # with httpx)
    console.print("Generating AI SITREP...")
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping AI generation")
        sitrep = "MOCK: SITREP generated without AI."
    else:
        if use_hq_model:
            selected_model = getattr(
                config.system,
                "ai_model_hq",
                config.system.ai_model,
            )
            selected_provider = "openai"
        else:
            selected_model = config.system.ai_model
            selected_provider = config.system.ai_provider

        monthly_budget = getattr(config.system, "ai_monthly_budget_usd", 10.0)
        cost_per_1k = getattr(config.system, "ai_cost_per_1k_tokens", 0.002)

        sitrep = await generate_sitrep(
            repo_id=repo_id,
            git_state=git_summary,
            terminal_logs=term_output,
            active_task=active_task,
            human_objective=human_objective,
            human_blocker=human_blocker,
            human_next_step=human_next_step,
            human_note=human_note,
            model=selected_model,
            provider=selected_provider,
            fallback_provider=config.system.ai_fallback_provider,
            fallback_model=config.system.ai_fallback_model,
            require_confirmation=config.system.ai_require_confirmation,
            openai_api_url=config.system.openai_api_url,
            openai_timeout_seconds=config.system.openai_timeout_seconds,
            openai_max_tokens=config.system.openai_max_tokens,
            api_url=config.system.ollama_api_url,
            timeout_seconds=config.system.ollama_timeout_seconds,
            max_retries=config.system.ollama_max_retries,
            backoff_seconds=config.system.ollama_backoff_seconds,
            db_path=config.system.db_path,
            monthly_budget_usd=monthly_budget,
            cost_per_1k_tokens=cost_per_1k,
        )
    logger.info(f"Generated SITREP for {repo_id}")

    # 5. Save to DB (Async)
    await init_db(config.system.db_path)
    async for session in get_session(config.system.db_path):
        # Ensure Repository exists (FK constraint)
        from prime_directive.core.db import Repository
        from sqlalchemy import select as sql_select

        repo_id_col = cast(Any, Repository.id)
        stmt = sql_select(Repository).where(repo_id_col == repo_id)
        result = await session.execute(stmt)
        existing_repo = result.scalars().first()
        if not existing_repo:
            new_repo = Repository(
                id=repo_id,
                path=repo_path,
                priority=repo_config.priority,
                active_branch=repo_config.active_branch,
            )
            session.add(new_repo)
            await session.flush()

        snapshot = ContextSnapshot(
            repo_id=repo_id,
            timestamp=datetime.now(timezone.utc),
            git_status_summary=git_summary,
            terminal_last_command=last_cmd,
            terminal_output_summary=term_output,
            ai_sitrep=sitrep,
            human_note=human_note,
            human_objective=human_objective,
            human_blocker=human_blocker,
            human_next_step=human_next_step,
        )
        session.add(snapshot)
        await session.commit()
        msg = f"Snapshot saved. ID: {snapshot.id}"
        console.print(f"[bold green]{msg}[/bold green]")
        if human_objective:
            console.print(
                "[bold magenta]YOUR OBJECTIVE:[/bold magenta] "
                f"{human_objective}"
            )
        if human_blocker:
            console.print(
                "[bold magenta]YOUR BLOCKER:[/bold magenta] "
                f"{human_blocker}"
            )
        if human_next_step:
            console.print(
                "[bold magenta]YOUR NEXT STEP:[/bold magenta] "
                f"{human_next_step}"
            )
        if human_note:
            console.print(
                f"[bold magenta]YOUR NOTE:[/bold magenta] {human_note}"
            )
        console.print(f"[italic]{sitrep}[/italic]")
        logger.info(f"{msg}. SITREP: {sitrep}. Note: {human_note}")


@app.command("freeze")
def freeze(
    repo_id: str,
    objective: Optional[str] = typer.Option(
        None,
        "--objective",
        help="Primary objective of this session",
    ),
    blocker: Optional[str] = typer.Option(
        None,
        "--blocker",
        help="What didn't work / key uncertainty",
    ),
    next_step: Optional[str] = typer.Option(
        None,
        "--next-step",
        help="Next concrete action",
    ),
    note: Optional[str] = typer.Option(
        None,
        "--note",
        "-n",
        help="Optional: additional notes / brain dump",
    ),
    no_interview: bool = typer.Option(
        False,
        "--no-interview",
        help="Disable interactive interview prompts",
    ),
    hq: bool = typer.Option(
        False,
        "--hq",
        help="Use high-quality AI model (more expensive, better results)",
    ),
):
    """
    Create a repository snapshot (Git, terminal, and active task) and generate an AI SITREP; prompts the user for optional human context unless disabled.
    
    Parameters:
        repo_id (str): Identifier of the repository to snapshot.
        objective (Optional[str]): Primary focus for this session; included in the snapshot/SITREP.
        blocker (Optional[str]): Key blocker, uncertainty, or gotcha to record.
        next_step (Optional[str]): First concrete action to restart work, recorded as the next step.
        note (Optional[str]): Additional notes or brain dump to include in the snapshot and AI summary.
        no_interview (bool): If True, skip interactive prompts and use provided values as-is.
        hq (bool): If True, request the higher-quality (higher-cost) AI model for SITREP generation.
    """
    logger.info(f"Command: freeze {repo_id}")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    repo_id = _resolve_repo_id(repo_id, cfg)

    if not no_interview:
        if objective is None:
            entered = typer.prompt(
                "Context: What was your specific focus vs. the planned task?",
                default="",
                show_default=False,
            )
            objective = entered.strip() or None

        if blocker is None:
            entered = typer.prompt(
                "Mental Cache: What is the key blocker, uncertainty, or "
                "'gotcha'?",
                default="",
                show_default=False,
            )
            blocker = entered.strip() or None

        if next_step is None:
            entered = typer.prompt(
                "The Hook: What is the first 10-second action to restart?",
                default="",
                show_default=False,
            )
            next_step = entered.strip() or None

        if note is None:
            entered = typer.prompt(
                "Brain Dump: Any other context, warnings, or loose thoughts?",
                default="",
                show_default=False,
            )
            note = entered.strip() or None

    async def run_freeze():
        """
        Run the freeze logic for the selected repository and ensure DB engine disposal.
        
        Calls `freeze_logic` with the surrounding command options (note, objective, blocker, next_step, HQ flag). If `freeze_logic` raises a `ValueError`, exits the Typer command with code 1. Always disposes the database engine by awaiting `dispose_engine()` in a finally block.
        """
        try:
            await freeze_logic(
                repo_id,
                cfg,
                human_note=note,
                human_objective=objective,
                human_blocker=blocker,
                human_next_step=next_step,
                use_hq_model=hq,
            )
        except ValueError:
            raise typer.Exit(code=1) from None
        finally:
            await dispose_engine()

    asyncio.run(run_freeze())


@app.command("switch")
def switch(repo_id: str):
    """
    Switch the active workspace to another repository by freezing the current repo, performing the switch, and preparing the target repo.
    
    Raises:
    	typer.Exit: With code 1 if `repo_id` is not present in configuration; with `_EXIT_CODE_SHELL_ATTACH` if the switch requires attaching a new shell.
    """
    logger.info(f"Command: switch {repo_id}")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    repo_id = _resolve_repo_id(repo_id, cfg)

    needs_shell_attach = run_switch(
        repo_id,
        cfg,
        cwd=os.getcwd(),
        freeze_fn=freeze_logic,
        ensure_session_fn=ensure_session,
        launch_editor_fn=launch_editor,
        init_db_fn=init_db,
        get_session_fn=get_session,
        dispose_engine_fn=dispose_engine,
        console=console,
        logger=logger,
    )

    if needs_shell_attach:
        raise typer.Exit(code=_EXIT_CODE_SHELL_ATTACH)


@app.command("install-hooks")
def install_hooks(repo_id: Optional[str] = typer.Argument(None)):
    """
    Install a Git post-commit hook that logs commits for a single configured repository or for all configured repositories.
    
    Creates a "post-commit" script under each target repository's .git/hooks directory that invokes the internal `pd _internal-log-commit <repo_id>` command, and makes the script executable.
    
    Parameters:
        repo_id (Optional[str]): If provided, install the hook only for the repository with this config ID; if `None`, install hooks for all repositories defined in the configuration.
    
    Raises:
        typer.Exit: Exits with code 1 if the specified repo_id is not found in the configuration, if the target path is not a Git repository (missing `.git`), or if filesystem operations fail while creating or writing the hook.
    """
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    if repo_id is not None:
        repo_id = _resolve_repo_id(repo_id, cfg)

    target_repo_ids = (
        [repo_id] if repo_id is not None else list(cfg.repos.keys())
    )

    for rid in target_repo_ids:
        repo_path = cfg.repos[rid].path
        git_dir = os.path.join(repo_path, ".git")
        hooks_dir = os.path.join(git_dir, "hooks")
        hook_path = os.path.join(hooks_dir, "post-commit")

        if not os.path.isdir(git_dir):
            msg = f"{rid}: not a git repo (missing .git): {repo_path}"
            console.print(f"[bold red]Error:[/bold red] {msg}")
            logger.error(msg)
            raise typer.Exit(code=1)

        try:
            os.makedirs(hooks_dir, exist_ok=True)

            script = (
                "#!/bin/sh\n"
                f"command pd _internal-log-commit {rid} "
                ">/dev/null 2>&1 || true\n"
            )
            with open(hook_path, "w", encoding="utf-8") as f:
                f.write(script)

            os.chmod(hook_path, 0o755)

            console.print(
                f"[green]Installed post-commit hook:[/green] {hook_path}"
            )
            logger.info(f"Installed post-commit hook for {rid}: {hook_path}")
        except OSError as e:
            msg = f"{rid}: failed to install post-commit hook: {e}"
            console.print(f"[bold red]Error:[/bold red] {msg}")
            logger.exception(msg)
            raise typer.Exit(code=1) from None


@app.command("_internal-log-commit", hidden=True)
def internal_log_commit(repo_id: str):
    """
    Record a commit event for the given repository in the application's event log.
    
    This creates and persists an EventLog entry with EventType.COMMIT associated with the provided repository identifier using the configured database, and ensures database resources are cleaned up.
    
    Parameters:
        repo_id (str): Identifier of the repository to associate with the commit event.
    """
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    async def run_internal():
        """
        Record a commit event for the current repository in the application's database.
        
        Initializes the database connection, inserts an EventLog with EventType.COMMIT for the enclosing `repo_id`, commits the change, and ensures the database engine is disposed on exit.
        """
        try:
            await init_db(cfg.system.db_path)
            async for session in get_session(cfg.system.db_path):
                session.add(
                    EventLog(
                        repo_id=repo_id,
                        event_type=EventType.COMMIT,
                    )
                )
                await session.commit()
        finally:
            await dispose_engine()

    asyncio.run(run_internal())


def _format_seconds(seconds: float) -> str:
    """
    Format a duration in seconds into a compact human-readable string.
    
    Converts the given number of seconds to hours, minutes, and seconds and returns:
    - "HhMMmSSs" when one hour or more,
    - "MmSSs" when at least one minute but less than an hour,
    - "Ss" when less than one minute.
    
    Parameters:
        seconds (float): Duration in seconds.
    
    Returns:
        str: Formatted duration string, e.g. "1h02m03s", "12m34s", or "45s".
    """
    seconds_int = round(seconds)
    hours, rem = divmod(seconds_int, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes > 0:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


@app.command("metrics")
def metrics(repo_id: Optional[str] = typer.Option(None, "--repo")):
    """
    Display time-to-commit metrics for one or all configured repositories.
    
    Calculates intervals between a SWITCH_IN event and the next COMMIT event to derive average and most recent time-to-commit (TTC) and the number of samples for each repository, then prints a summary table to the console. When a `repo_id` is provided, metrics are limited to that repository.
    Parameters:
        repo_id (Optional[str]): Repository identifier to limit the report to a single repository; when omitted, metrics for all configured repositories are shown.
    """
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    if repo_id is not None:
        repo_id = _resolve_repo_id(repo_id, cfg)

    async def run_metrics():
        """
        Compute and display time-to-commit (TTC) metrics for one or all repositories.
        
        Initializes the database, collects EventLog entries for the specified repo_id (or all repos if none provided), computes intervals from each SWITCH_IN event to the next COMMIT event, and prints a table showing the average TTC, the most recent TTC, and the sample count for each repository. Ensures the database engine is disposed on completion.
        """
        try:
            await init_db(cfg.system.db_path)

            target_repo_ids = (
                [repo_id] if repo_id is not None else list(cfg.repos.keys())
            )

            table = Table(title="Prime Directive Metrics")
            table.add_column("Repo", style="cyan")
            table.add_column("TTC avg", style="green")
            table.add_column("TTC recent", style="magenta")
            table.add_column("Samples", justify="right")

            async for session in get_session(cfg.system.db_path):
                for rid in target_repo_ids:
                    stmt = (
                        select(EventLog)
                        .where(EventLog.repo_id == rid)
                        .order_by(EventLog.timestamp.asc())
                    )
                    result = await session.execute(stmt)
                    events = list(result.scalars().all())

                    deltas: list[float] = []
                    last_switch_ts: Optional[datetime] = None
                    for ev in events:
                        if ev.event_type == EventType.SWITCH_IN:
                            last_switch_ts = ev.timestamp
                        elif (
                            ev.event_type == EventType.COMMIT
                            and last_switch_ts is not None
                        ):
                            delta = (
                                ev.timestamp - last_switch_ts
                            ).total_seconds()
                            if delta >= 0:
                                deltas.append(delta)
                            last_switch_ts = None

                    if deltas:
                        avg = sum(deltas) / len(deltas)
                        recent = deltas[-1]
                        table.add_row(
                            rid,
                            _format_seconds(avg),
                            _format_seconds(recent),
                            str(len(deltas)),
                        )
                    else:
                        table.add_row(rid, "-", "-", "0")

            console.print(table)
        finally:
            await dispose_engine()

    asyncio.run(run_metrics())


@app.command("list")
def list_repos():
    """
    Display a table of all managed repositories.
    
    Prints a Rich table showing each repository's ID, priority, active branch (or "N/A"), and filesystem path. Repositories are sorted by priority in descending order.
    """
    logger.info("Command: list")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    table = Table(title="Prime Directive Repositories")
    table.add_column("ID", style="cyan")
    table.add_column("Priority", style="magenta")
    table.add_column("Branch", style="green")
    table.add_column("Path", style="yellow")

    # Sort by priority descending
    sorted_repos = sorted(
        cfg.repos.values(),
        key=lambda r: r.priority,
        reverse=True,
    )

    for repo in sorted_repos:
        table.add_row(
            repo.id,
            str(repo.priority),
            repo.active_branch or "N/A",
            repo.path,
        )
    console.print(table)


@app.command("status")
def status_command():
    """Show detailed status of all repositories."""
    logger.info("Command: status")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    table = Table(title="Prime Directive Status")
    table.add_column("Project", style="cyan")
    table.add_column("Priority", justify="center")
    table.add_column("Branch", style="green")
    table.add_column("Git Status", style="bold")
    table.add_column("Last Snapshot", style="blue")

    sorted_repos = sorted(
        cfg.repos.values(),
        key=lambda r: r.priority,
        reverse=True,
    )

    async def run_status():
        """
        Collects repository statuses and populates the display table with git state and last snapshot timestamps.
        
        This coroutine initializes the database, iterates configured repositories, obtains each repository's git status and most recent ContextSnapshot timestamp, and adds a row to the shared table containing repository id, priority, branch, git status, and last snapshot time. The database engine is always disposed when finished.
        """
        try:
            # Ensure DB exists/tables created
            await init_db(cfg.system.db_path)

            async for session in get_session(cfg.system.db_path):
                # We can reuse this session for all queries

                for repo in sorted_repos:
                    # 1. Git Status (Sync)
                    if cfg.system.mock_mode:
                        git_st = {
                            "branch": "mock",
                            "is_dirty": False,
                            "uncommitted_files": [],
                        }
                    else:
                        git_st = await get_status(repo.path)

                    status_icon = "🟢"
                    status_text = "Clean"
                    if git_st["is_dirty"]:
                        status_icon = "🔴"
                        dirty_count = len(git_st["uncommitted_files"])
                        status_text = f"Dirty ({dirty_count})"
                    elif git_st["branch"] == "unknown":
                        status_icon = "⚪"
                        status_text = "Not Git"
                    elif git_st["branch"] == "error":
                        status_icon = "❌"
                        status_text = "Error"
                    elif git_st["branch"] == "timeout":
                        status_icon = "⏱️"
                        status_text = "Timeout"

                    git_display = f"{status_icon} {status_text}"

                    # 2. Last Snapshot (Async)
                    last_snap_str = "Never"
                    try:
                        stmt = (
                            select(ContextSnapshot)
                            .where(ContextSnapshot.repo_id == repo.id)
                            .order_by(ContextSnapshot.timestamp.desc())
                            .limit(1)
                        )
                        result = await session.execute(stmt)
                        snapshot = result.scalars().first()
                        if snapshot:
                            ts_fmt = "%Y-%m-%d %H:%M"
                            last_snap_str = snapshot.timestamp.strftime(ts_fmt)
                    except (OSError, ValueError) as e:
                        logger.warning(
                            f"Error fetching snapshot for {repo.id}: {e}"
                        )
                        last_snap_str = "Error"

                    if repo.priority >= 8:
                        priority_prefix = "🔥"
                    else:
                        priority_prefix = "⚡"
                    priority_display = f"{priority_prefix} {repo.priority}"
                    if isinstance(git_st["branch"], str):
                        branch_display = git_st["branch"]
                    else:
                        branch_display = "Unknown"

                    table.add_row(
                        repo.id,
                        priority_display,
                        branch_display,
                        git_display,
                        last_snap_str,
                    )
        finally:
            await dispose_engine()

    asyncio.run(run_status())
    console.print(table)


@app.command("sitrep")
def sitrep(
    repo_id: str,
    deep_dive: bool = typer.Option(
        False,
        "--deep-dive",
        help=(
            "Generate longitudinal summary from historical snapshots "
            "using HQ model"
        ),
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-l",
        help="Number of historical snapshots to include (default: 5)",
    ),
):
    """
    Show a situational report (SITREP) for a repository.
    
    If deep_dive is enabled, compile recent historical snapshots and produce a longitudinal
    SITREP using the configured high-quality AI model; deep-dive requires a valid OpenAI API key.
    When not deep-diving, display the latest snapshot's timestamp, optional human-provided
    fields (objective, blocker, next step, note), and the AI summary.
    
    Parameters:
        repo_id (str): Identifier of the repository to inspect.
        deep_dive (bool): When True, generate a longitudinal summary from historical snapshots.
        limit (int): Number of most-recent snapshots to include in the deep-dive analysis.
    """
    logger.info(f"Command: sitrep {repo_id} (deep_dive={deep_dive})")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    repo_id = _resolve_repo_id(repo_id, cfg)

    async def run_sitrep():
        """
        Show recent context snapshots for the configured repository and, if requested, produce an HQ deep-dive SITREP.
        
        Initializes the database, retrieves up to `limit` ContextSnapshot records for `repo_id`, and prints either a brief SITREP of the latest snapshot (timestamp, human objective/blocker/next step/note, and AI summary) or a longitudinal deep-dive. For deep dives, the function compiles a historical narrative from the snapshots and calls the OpenAI-based chat generator (requires OPENAI_API_KEY) to produce a concise longitudinal summary; any errors from the AI call are printed. The database engine is always disposed on exit.
        """
        await init_db(cfg.system.db_path)
        try:
            async for session in get_session(cfg.system.db_path):
                repo_id_col = cast(Any, ContextSnapshot.repo_id)
                ts_col = cast(Any, ContextSnapshot.timestamp)
                stmt = (
                    select(ContextSnapshot)
                    .where(repo_id_col == repo_id)
                    .order_by(ts_col.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                snapshots = list(result.scalars().all())

                if not snapshots:
                    console.print(
                        f"[yellow]No snapshots found for {repo_id}[/yellow]"
                    )
                    return

                if not deep_dive:
                    # Just show the latest snapshot
                    latest = snapshots[0]
                    console.print(
                        f"\n[bold reverse] SITREP for {repo_id} "
                        "[/bold reverse]"
                    )
                    console.print(
                        f"[bold yellow]Timestamp:[/bold yellow] "
                        f"{latest.timestamp}"
                    )
                    if latest.human_objective:
                        console.print(
                            "[bold magenta]Objective:[/bold magenta] "
                            f"{latest.human_objective}"
                        )
                    if latest.human_blocker:
                        console.print(
                            "[bold magenta]Blocker:[/bold magenta] "
                            f"{latest.human_blocker}"
                        )
                    if latest.human_next_step:
                        console.print(
                            "[bold magenta]Next Step:[/bold magenta] "
                            f"{latest.human_next_step}"
                        )
                    if latest.human_note:
                        console.print(
                            "[bold magenta]Note:[/bold magenta] "
                            f"{latest.human_note}"
                        )
                    console.print(
                        "[bold cyan]AI Summary:[/bold cyan] "
                        f"{latest.ai_sitrep}"
                    )
                    return

                # Deep dive: compile historical narrative
                console.print(
                    "[bold blue]Generating deep-dive analysis for "
                    f"{repo_id}...[/bold blue]"
                )
                console.print(
                    f"[dim]Analyzing {len(snapshots)} historical snapshots..."
                    "[/dim]"
                )

                # Build historical narrative
                history_entries = []
                for i, snap in enumerate(reversed(snapshots)):  # oldest first
                    entry = f"--- Snapshot {i+1} ({snap.timestamp}) ---\n"
                    if snap.human_objective:
                        entry += f"Objective: {snap.human_objective}\n"
                    if snap.human_blocker:
                        entry += f"Blocker: {snap.human_blocker}\n"
                    if snap.human_next_step:
                        entry += f"Next Step: {snap.human_next_step}\n"
                    if snap.human_note:
                        entry += f"Notes: {snap.human_note}\n"
                    entry += f"AI Summary: {snap.ai_sitrep}\n"
                    entry += f"Git State: {snap.git_status_summary}\n"
                    history_entries.append(entry)

                historical_narrative = "\n".join(history_entries)

                # Generate longitudinal summary using HQ model
                from prime_directive.core.ai_providers import (
                    generate_openai_chat,
                    get_openai_api_key,
                )

                api_key = get_openai_api_key()
                if not api_key:
                    console.print(
                        "[bold red]Error:[/bold red] OPENAI_API_KEY not set "
                        "(required for deep-dive)"
                    )
                    return

                system_prompt = (
                    "You are a senior engineering assistant "
                    "analyzing a developer's work history. "
                    "Given a series of timestamped context "
                    "snapshots, generate a comprehensive "
                    "longitudinal summary that: "
                    "1) Identifies the overarching goals, "
                    "2) Highlights what approaches were tried "
                    "and failed, "
                    "3) Notes key blockers and uncertainties, "
                    "4) Recommends the immediate next action "
                    "based on the trajectory. "
                    "Be specific and actionable. Max 200 words."
                )

                prompt = f"""
Repository: {repo_id}
Number of snapshots: {len(snapshots)}
Time span: {snapshots[-1].timestamp} to {snapshots[0].timestamp}

Historical Context (oldest to newest):
{historical_narrative}

Generate a longitudinal SITREP that helps the developer resume work
effectively.
"""

                hq_model = getattr(cfg.system, "ai_model_hq", "gpt-4o")
                try:
                    summary = await generate_openai_chat(
                        api_url=cfg.system.openai_api_url,
                        api_key=api_key,
                        model=hq_model,
                        system=system_prompt,
                        prompt=prompt,
                        timeout_seconds=30.0,
                        max_tokens=500,
                    )

                    console.print(
                        f"\n[bold reverse] DEEP-DIVE SITREP for {repo_id} "
                        "[/bold reverse]"
                    )

                    time_span = (
                        f"{snapshots[-1].timestamp} to "
                        f"{snapshots[0].timestamp}"
                    )
                    console.print(
                        f"[dim]Based on {len(snapshots)} snapshots from "
                        f"{time_span}"
                        "[/dim]"
                    )
                    console.print(f"\n[bold cyan]{summary}[/bold cyan]")
                except (httpx.HTTPError, ValueError, OSError) as e:
                    console.print(
                        "[bold red]Error generating deep-dive:[/bold red] "
                        f"{e}"
                    )
        finally:
            await dispose_engine()

    asyncio.run(run_sitrep())


@app.command("ai-usage")
def ai_usage():
    """
    Print a month-to-date AI usage and budget report to the console.
    
    Includes the total estimated cost and call count for the current month, the configured monthly budget and remaining balance with a color-coded usage warning, and a table of up to 10 recent AI call logs showing time, provider, model, tokens, cost, and success status.
    """
    logger.info("Command: ai-usage")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    from prime_directive.core.ai_providers import get_monthly_usage
    from prime_directive.core.db import AIUsageLog

    async def run_usage():
        """
        Display a month-to-date AI usage report and recent API calls.
        
        Queries stored AI usage metrics, prints totals (calls, cost, budget, remaining and usage percentage)
        and a table of recent API calls to the console, and ensures the database engine is initialized
        and disposed.
        """
        await init_db(cfg.system.db_path)
        try:
            # Get monthly totals
            total_cost, call_count = await get_monthly_usage(
                cfg.system.db_path
            )
            budget = getattr(cfg.system, "ai_monthly_budget_usd", 10.0)
            remaining = max(0, budget - total_cost)
            pct_used = (total_cost / budget * 100) if budget > 0 else 0

            console.print("\n[bold reverse] AI Usage Report [/bold reverse]")
            console.print("[bold]Month-to-Date (OpenAI):[/bold]")
            console.print(f"  Calls: {call_count}")
            console.print(f"  Cost:  ${total_cost:.4f}")
            console.print(f"  Budget: ${budget:.2f}")
            console.print(
                f"  Remaining: ${remaining:.4f} ({100-pct_used:.1f}%)"
            )

            if pct_used >= 90:
                console.print(
                    "  [bold red]⚠️  "
                    f"{pct_used:.1f}% of budget used!"
                    "[/bold red]"
                )
            elif pct_used >= 75:
                console.print(
                    "  [bold yellow]⚠️  "
                    f"{pct_used:.1f}% of budget used"
                    "[/bold yellow]"
                )
            else:
                console.print(
                    "  [green]✅ " f"{pct_used:.1f}% of budget used" "[/green]"
                )

            # Show recent calls
            async for session in get_session(cfg.system.db_path):
                now = datetime.now(timezone.utc)
                month_start = now.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                ts_col = cast(Any, AIUsageLog.timestamp)
                stmt = (
                    select(AIUsageLog)
                    .where(ts_col >= month_start)
                    .order_by(ts_col.desc())
                    .limit(10)
                )
                result = await session.execute(stmt)
                recent = list(result.scalars().all())

                if recent:
                    console.print("\n[bold]Recent Calls:[/bold]")
                    table = Table(show_header=True)
                    table.add_column("Time", style="dim")
                    table.add_column("Provider")
                    table.add_column("Model")
                    table.add_column("Tokens")
                    table.add_column("Cost")
                    table.add_column("Status")

                    for log in recent:
                        status = (
                            "[green]✓[/green]"
                            if log.success
                            else "[red]✗[/red]"
                        )
                        table.add_row(
                            log.timestamp.strftime("%m-%d %H:%M"),
                            log.provider,
                            log.model,
                            str(log.output_tokens),
                            f"${log.cost_estimate_usd:.4f}",
                            status,
                        )
                    console.print(table)
                break
        finally:
            await dispose_engine()

    asyncio.run(run_usage())


@app.command("doctor")
def doctor():
    """Diagnose system dependencies and configuration."""
    logger.info("Command: doctor")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    console.print("[bold]Prime Directive Doctor[/bold]")
    if cfg.system.mock_mode:
        console.print("[bold yellow]MOCK MODE ENABLED[/bold yellow]")

    checks = []

    # 1. Tmux
    if cfg.system.mock_mode:
        checks.append(("Tmux Installed", "✅", "Mocked"))
    else:
        tmux_path = shutil.which("tmux")
        checks.append(
            (
                "Tmux Installed",
                "✅" if tmux_path else "❌",
                tmux_path or "Not found",
            )
        )

    # 2. Editor
    if cfg.system.mock_mode:
        checks.append((f"Editor ({cfg.system.editor_cmd})", "✅", "Mocked"))
    else:
        editor_cmd = cfg.system.editor_cmd
        editor_path = shutil.which(editor_cmd)
        checks.append(
            (
                f"Editor ({editor_cmd})",
                "✅" if editor_path else "❌",
                editor_path or "Not found in PATH",
            )
        )

    # 3. AI Model (Ollama)
    if cfg.system.mock_mode:
        checks.append(("AI Engine (Ollama)", "✅", "Mocked"))
    else:
        ollama = get_ollama_status(cfg.system.ai_model)
        if not ollama.installed:
            ai_status = "❌"
            ai_msg = f"{ollama.details}. Install: {ollama.install_cmd}"
        elif not ollama.running:
            ai_status = "❌"
            ai_msg = f"{ollama.details}. Start: {ollama.start_cmd}"
        else:
            if "missing" in ollama.details.lower():
                ai_status = "⚠️"
            else:
                ai_status = "✅"
            ai_msg = ollama.details
        checks.append(("AI Engine (Ollama)", ai_status, ai_msg))

    # 3b. OpenAI fallback availability (optional)
    if cfg.system.mock_mode:
        checks.append(("OpenAI Fallback", "✅", "Mocked"))
    else:
        if has_openai_api_key():
            checks.append(("OpenAI Fallback", "✅", "OPENAI_API_KEY set"))
        else:
            checks.append(("OpenAI Fallback", "⚠️", "OPENAI_API_KEY not set"))

    # 3c. Check for multiple pd installations (can cause config shadowing)
    if cfg.system.mock_mode:
        checks.append(("Installation", "✅", "Mocked"))
    else:
        pd_locations = []
        search_paths = [
            Path.home() / ".local" / "bin" / "pd",
            Path.home() / ".local" / "share" / "uv" / "tools" / "prime-directive",
            Path.home() / ".local" / "share" / "pipx" / "venvs" / "prime-directive",
        ]
        for p in search_paths:
            if p.exists():
                pd_locations.append(str(p))
        if pd_locations:
            checks.append((
                "Installation",
                "⚠️",
                f"Multiple installs detected: {', '.join(pd_locations)}. "
                "May cause config shadowing. Remove with: rm -rf <path>",
            ))
        else:
            checks.append(("Installation", "✅", "Single installation (editable)"))

    # 4. Registry Paths
    console.print("\n[bold]Checking Repositories:[/bold]")
    for repo in cfg.repos.values():
        exists = os.path.exists(repo.path)
        icon = "✅" if exists else "❌"
        console.print(f"  {icon} {repo.id}: {repo.path}")
        if not exists:
            checks.append((f"Repo {repo.id}", "❌", "Path not found"))

    console.print("\n[bold]System Checks:[/bold]")
    table = Table(show_header=False)
    for name, icon, msg in checks:
        table.add_row(name, icon, msg)
    console.print(table)

    # Log results
    logger.info(f"Doctor checks: {checks}")