import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
import typer

# Hydra imports
from hydra import compose, initialize
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig

# Core imports
from prime_directive.core.config import register_configs
from prime_directive.core.git_utils import get_status
from prime_directive.core.db import get_session, ContextSnapshot, init_db, dispose_engine
from prime_directive.core.terminal import capture_terminal_state
from prime_directive.core.tasks import get_active_task
from prime_directive.core.scribe import generate_sitrep
from prime_directive.core.tmux import ensure_session
from prime_directive.core.windsurf import launch_editor
from prime_directive.core.logging_utils import setup_logging
from prime_directive.core.orchestrator import run_switch
from prime_directive.core.dependencies import get_ollama_status, has_openai_api_key

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

def load_config() -> DictConfig:
    """Load configuration using Hydra."""
    # Ensure any previous Hydra instance is cleared
    GlobalHydra.instance().clear()
    
    # Register structured configs
    register_configs()
    
    # Initialize Hydra - use relative path from this module's location
    # ../conf is relative to prime_directive/bin/pd.py -> prime_directive/conf
    try:
        with initialize(version_base=None, config_path="../conf"):
            cfg = compose(config_name="config")
            return cfg
    except Exception as e:
        msg = f"Error loading config: {e}"
        console.print(f"[bold red]{msg}[/bold red]")
        logger.critical(msg)
        sys.exit(1)

# Initialize logging globally with default, will be re-configured if needed
setup_logging()

async def freeze_logic(repo_id: str, config: DictConfig, human_note: Optional[str] = None):
    """Core freeze logic separated for reuse (Async)."""
    if repo_id not in config.repos:
        msg = f"Repository '{repo_id}' not found in configuration."
        console.print(f"[bold red]Error:[/bold red] {msg}")
        logger.error(msg)
        # We can't raise Typer.Exit in async easily if we want to clean up, 
        # but for now we'll just return or raise an exception.
        raise ValueError(msg)

    repo_config = config.repos[repo_id]
    repo_path = repo_config.path

    logger.info(f"Freezing context for {repo_id} at {repo_path}")
    console.print(f"[bold blue]Freezing context for {repo_id}...[/bold blue]")

    # 1. Capture Git State (Sync/Blocking)
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping actual git status check")
        git_summary = "MOCK: Branch: main\nDirty: False"
        git_st = {
            "branch": "main",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": "",
        }
    else:
        git_st = get_status(repo_path)
        git_summary = (
            f"Branch: {git_st['branch']}\n"
            f"Dirty: {git_st['is_dirty']}\n"
            f"Files: {git_st['uncommitted_files']}\n"
            f"Diff: {git_st.get('diff_stat', '')}"
        )

    logger.debug(f"Git state for {repo_id}: {git_st}")

    # 2. Capture Terminal State (Sync/Blocking)
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping terminal capture")
        last_cmd = "mock_cmd"
        term_output = "MOCK: Terminal output"
    else:
        last_cmd, term_output = capture_terminal_state(repo_id)

    logger.debug(f"Terminal state: cmd={last_cmd}")

    # 3. Capture Active Task (Sync)
    active_task = get_active_task(repo_path)
    logger.debug(f"Active task: {active_task}")

    # 4. Generate AI SITREP (Blocking Network Call - could be made async with httpx)
    console.print("Generating AI SITREP...")
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping AI generation")
        sitrep = "MOCK: SITREP generated without AI."
    else:
        sitrep = generate_sitrep(
            repo_id=repo_id,
            git_state=git_summary,
            terminal_logs=term_output,
            active_task=active_task,
            model=config.system.ai_model,
            provider=config.system.ai_provider,
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
        )
    logger.info(f"Generated SITREP for {repo_id}")

    # 5. Save to DB (Async)
    await init_db(config.system.db_path)
    async for session in get_session(config.system.db_path):
        # Ensure Repository exists (FK constraint)
        from prime_directive.core.db import Repository
        from sqlalchemy import select as sql_select
        stmt = sql_select(Repository).where(Repository.id == repo_id)
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
        )
        session.add(snapshot)
        await session.commit()
        msg = f"Snapshot saved. ID: {snapshot.id}"
        console.print(f"[bold green]{msg}[/bold green]")
        console.print(f"[bold magenta]YOUR NOTE:[/bold magenta] {human_note}")
        console.print(f"[italic]{sitrep}[/italic]")
        logger.info(f"{msg}. SITREP: {sitrep}. Note: {human_note}")


@app.command("freeze")
def freeze(
    repo_id: str,
    note: str = typer.Option(
        ...,
        "--note",
        "-n",
        help=(
            "REQUIRED: What you were actually working on "
            "(AI can't read your mind)"
        ),
    ),
):
    """
    Snapshot the current state of a repository (Git, Terminal, Task) and generate an AI SITREP.
    
    The --note is MANDATORY. This is YOUR context that the AI will miss.
    Without it, you lose the most important piece of information: what YOU knew.
    
    Example: pd freeze my-repo --note "Fixing PR merge issues from CodeRabbit review"
    """
    logger.info(f"Command: freeze {repo_id}")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    async def run_freeze():
        try:
            await freeze_logic(repo_id, cfg, human_note=note)
        except ValueError:
            raise typer.Exit(code=1) from None
        finally:
            await dispose_engine()

    asyncio.run(run_freeze())


@app.command("switch")
def switch(repo_id: str):
    """
    Switch context to another repository (Freeze current -> Warp -> Thaw target).
    """
    logger.info(f"Command: switch {repo_id}")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    if repo_id not in cfg.repos:
        msg = f"Repository '{repo_id}' not found in configuration."
        console.print(f"[bold red]Error:[/bold red] {msg}")
        logger.error(msg)
        raise typer.Exit(code=1)

    run_switch(
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


@app.command("list")
def list_repos():
    """List all managed repositories."""
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
            repo.path
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

    sorted_repos = sorted(cfg.repos.values(), key=lambda r: r.priority, reverse=True)

    async def run_status():
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
                        git_st = get_status(repo.path)

                    status_icon = "🟢"
                    status_text = "Clean"
                    if git_st["is_dirty"]:
                        status_icon = "🔴"
                        status_text = f"Dirty ({len(git_st['uncommitted_files'])})"
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
                            last_snap_str = snapshot.timestamp.strftime("%Y-%m-%d %H:%M")
                    except (OSError, ValueError) as e:
                        logger.warning(f"Error fetching snapshot for {repo.id}: {e}")
                        last_snap_str = "Error"

                    priority_display = f"{'🔥' if repo.priority >= 8 else '⚡'} {repo.priority}"
                    if isinstance(git_st["branch"], str):
                        branch_display = git_st["branch"]
                    else:
                        branch_display = "Unknown"

                    table.add_row(
                        repo.id,
                        priority_display,
                        branch_display,
                        git_display,
                        last_snap_str
                    )
        finally:
            await dispose_engine()

    asyncio.run(run_status())
    console.print(table)


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
