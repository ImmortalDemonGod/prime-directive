import typer
import shutil
import requests
import os
import sys
import logging
from rich.console import Console
from rich.table import Table
from typing import Optional
from pathlib import Path
import asyncio
from sqlalchemy import select
from datetime import datetime

# Hydra imports
from hydra import compose, initialize
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf, DictConfig

# Core imports
from prime_directive.core.config import PrimeConfig, register_configs
from prime_directive.core.git_utils import get_status
from prime_directive.core.db import get_session, ContextSnapshot, init_db
from prime_directive.core.terminal import capture_terminal_state
from prime_directive.core.tasks import get_active_task
from prime_directive.core.scribe import generate_sitrep
from prime_directive.core.tmux import ensure_session
from prime_directive.core.windsurf import launch_editor
from prime_directive.core.logging_utils import setup_logging

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
    
    # Initialize Hydra
    try:
        config_dir = Path(__file__).parent.parent / "conf"
        # Hydra expects relative path from the calling script or absolute path
        with initialize(version_base=None, config_path=str(config_dir)):
            cfg = compose(config_name="config")
            return cfg
    except Exception as e:
        # Fallback for when running from root or different context
        try:
            with initialize(version_base=None, config_path="../../prime_directive/conf"):
                cfg = compose(config_name="config")
                return cfg
        except Exception as inner_e:
             msg = f"Error loading config: {e} | {inner_e}"
             console.print(f"[bold red]{msg}[/bold red]")
             logger.critical(msg)
             sys.exit(1)

# Initialize logging globally
setup_logging()

def freeze_logic(repo_id: str, config: DictConfig):
    """Core freeze logic separated for reuse."""
    if repo_id not in config.repos:
        msg = f"Repository '{repo_id}' not found in configuration."
        console.print(f"[bold red]Error:[/bold red] {msg}")
        logger.error(msg)
        raise typer.Exit(code=1)

    repo_config = config.repos[repo_id]
    repo_path = repo_config.path
    
    logger.info(f"Freezing context for {repo_id} at {repo_path}")
    console.print(f"[bold blue]Freezing context for {repo_id}...[/bold blue]")
    
    # 1. Capture Git State
    git_st = get_status(repo_path)
    git_summary = f"Branch: {git_st['branch']}\nDirty: {git_st['is_dirty']}\nFiles: {git_st['uncommitted_files']}\nDiff: {git_st.get('diff_stat', '')}"
    logger.debug(f"Git state for {repo_id}: {git_st}")
    
    # 2. Capture Terminal State
    last_cmd, term_output = capture_terminal_state()
    logger.debug(f"Terminal state: cmd={last_cmd}")
    
    # 3. Capture Active Task
    active_task = get_active_task(repo_path)
    logger.debug(f"Active task: {active_task}")
    
    # 4. Generate AI SITREP
    console.print("Generating AI SITREP...")
    sitrep = generate_sitrep(
        repo_id=repo_id,
        git_state=git_summary,
        terminal_logs=term_output,
        active_task=active_task,
        model=config.system.ai_model
    )
    logger.info(f"Generated SITREP for {repo_id}")
    
    # 5. Save to DB
    async def save_snapshot():
        await init_db(config.system.db_path)
        async for session in get_session(config.system.db_path):
            snapshot = ContextSnapshot(
                repo_id=repo_id,
                timestamp=datetime.utcnow(),
                git_status_summary=git_summary,
                terminal_last_command=last_cmd,
                terminal_output_summary=term_output,
                ai_sitrep=sitrep
            )
            session.add(snapshot)
            await session.commit()
            msg = f"Snapshot saved. ID: {snapshot.id}"
            console.print(f"[bold green]{msg}[/bold green]")
            console.print(f"[italic]{sitrep}[/italic]")
            logger.info(f"{msg}. SITREP: {sitrep}")

    asyncio.run(save_snapshot())

@app.command("freeze")
def freeze(repo_id: str):
    """
    Snapshot the current state of a repository (Git, Terminal, Task) and generate an AI SITREP.
    """
    logger.info(f"Command: freeze {repo_id}")
    cfg = load_config()
    freeze_logic(repo_id, cfg)

@app.command("switch")
def switch(repo_id: str):
    """
    Switch context to another repository (Freeze current -> Warp -> Thaw target).
    """
    logger.info(f"Command: switch {repo_id}")
    cfg = load_config()
    
    if repo_id not in cfg.repos:
        msg = f"Repository '{repo_id}' not found in configuration."
        console.print(f"[bold red]Error:[/bold red] {msg}")
        logger.error(msg)
        raise typer.Exit(code=1)

    target_repo = cfg.repos[repo_id]

    # 1. Detect and Freeze current repo
    cwd = os.getcwd()
    current_repo_id = None
    for r_id, r_config in cfg.repos.items():
        # Check if CWD is inside the repo path
        if cwd.startswith(os.path.abspath(r_config.path)):
            current_repo_id = r_id
            break
    
    if current_repo_id and current_repo_id != repo_id:
        console.print(f"[yellow]Detected current repo: {current_repo_id}[/yellow]")
        logger.info(f"Auto-freezing current repo: {current_repo_id}")
        freeze_logic(current_repo_id, cfg)
    
    # 2. Thaw / Switch
    console.print(f"[bold green]>>> WARPING TO {repo_id.upper()} >>>[/bold green]")
    logger.info(f"Switching to {repo_id}")
    
    # Ensure Tmux Session
    ensure_session(repo_id, target_repo.path)
    
    # Launch Editor
    launch_editor(target_repo.path, cfg.system.editor_cmd)
    
    # 3. Display SITREP
    async def show_sitrep():
        await init_db(cfg.system.db_path)
        async for session in get_session(cfg.system.db_path):
            stmt = select(ContextSnapshot).where(ContextSnapshot.repo_id == repo_id).order_by(ContextSnapshot.timestamp.desc()).limit(1)
            result = await session.execute(stmt)
            snapshot = result.scalars().first()
            
            console.print("\n[bold reverse] SITREP [/bold reverse]")
            if snapshot:
                console.print(f"[bold cyan]>>> LAST ACTION:[/bold cyan] {snapshot.ai_sitrep}")
                console.print(f"[bold yellow]>>> TIMESTAMP:[/bold yellow] {snapshot.timestamp}")
            else:
                console.print("[italic]No previous snapshot found.[/italic]")
                
    asyncio.run(show_sitrep())

@app.command("list")
def list_repos():
    """List all managed repositories."""
    logger.info("Command: list")
    cfg = load_config()
    table = Table(title="Prime Directive Repositories")
    table.add_column("ID", style="cyan")
    table.add_column("Priority", style="magenta")
    table.add_column("Branch", style="green")
    table.add_column("Path", style="yellow")

    # Sort by priority descending
    sorted_repos = sorted(cfg.repos.values(), key=lambda r: r.priority, reverse=True)

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
    table = Table(title="Prime Directive Status")
    table.add_column("Project", style="cyan")
    table.add_column("Priority", justify="center")
    table.add_column("Branch", style="green")
    table.add_column("Git Status", style="bold")
    table.add_column("Last Snapshot", style="blue")

    sorted_repos = sorted(cfg.repos.values(), key=lambda r: r.priority, reverse=True)

    async def fetch_last_snapshot_time(repo_id: str, db_path: str) -> str:
        try:
            # Ensure DB exists/tables created
            await init_db(db_path)
            async for session in get_session(db_path):
                stmt = select(ContextSnapshot).where(ContextSnapshot.repo_id == repo_id).order_by(ContextSnapshot.timestamp.desc()).limit(1)
                result = await session.execute(stmt)
                snapshot = result.scalars().first()
                if snapshot:
                    return snapshot.timestamp.strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            logger.debug(f"Error fetching snapshot for {repo_id}: {e}")
            return "Unknown"
        return "Never"

    for repo in sorted_repos:
        # 1. Git Status
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
        
        # 2. Last Snapshot (Async wrapper)
        last_snap = asyncio.run(fetch_last_snapshot_time(repo.id, cfg.system.db_path))

        priority_display = f"{'🔥' if repo.priority >= 8 else '⚡'} {repo.priority}"

        table.add_row(
            repo.id,
            priority_display,
            git_st["branch"] if isinstance(git_st["branch"], str) else "Unknown",
            git_display,
            last_snap
        )

    console.print(table)

@app.command("doctor")
def doctor():
    """Diagnose system dependencies and configuration."""
    logger.info("Command: doctor")
    cfg = load_config()
    console.print("[bold]Prime Directive Doctor[/bold]")
    
    checks = []
    
    # 1. Tmux
    tmux_path = shutil.which("tmux")
    checks.append(("Tmux Installed", "✅" if tmux_path else "❌", tmux_path or "Not found"))

    # 2. Editor
    editor_cmd = cfg.system.editor_cmd
    editor_path = shutil.which(editor_cmd)
    checks.append((f"Editor ({editor_cmd})", "✅" if editor_path else "❌", editor_path or "Not found in PATH"))

    # 3. AI Model (Ollama)
    ai_status = "❌"
    ai_msg = "Connection Failed"
    try:
        # Check connection
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            target_model = cfg.system.ai_model
            # Check for partial match (e.g. qwen2.5-coder:latest)
            if any(target_model in name for name in model_names):
                ai_status = "✅"
                ai_msg = f"Connected & {target_model} found"
            else:
                ai_status = "⚠️"
                ai_msg = f"Connected but {target_model} missing (Pulling needed)"
        else:
            ai_msg = f"API Error: {resp.status_code}"
    except requests.exceptions.ConnectionError:
        ai_msg = "Ollama not running (localhost:11434)"
    except Exception as e:
        ai_msg = f"Error: {str(e)}"
    
    checks.append(("AI Engine (Ollama)", ai_status, ai_msg))

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

if __name__ == "__main__":
    app()
