import typer
import shutil
import requests
import os
from rich.console import Console
from rich.table import Table
from typing import Optional
from pathlib import Path
import asyncio
from sqlalchemy import select

from prime_directive.core.registry import load_registry
from prime_directive.core.git_utils import get_status
from prime_directive.core.db import get_session, ContextSnapshot, init_db

app = typer.Typer()
console = Console()

@app.command("list")
def list_repos():
    """List all managed repositories."""
    registry = load_registry()
    table = Table(title="Prime Directive Repositories")
    table.add_column("ID", style="cyan")
    table.add_column("Priority", style="magenta")
    table.add_column("Branch", style="green")
    table.add_column("Path", style="yellow")

    # Sort by priority descending
    sorted_repos = sorted(registry.repos.values(), key=lambda r: r.priority, reverse=True)

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
    registry = load_registry()
    table = Table(title="Prime Directive Status")
    table.add_column("Project", style="cyan")
    table.add_column("Priority", justify="center")
    table.add_column("Branch", style="green")
    table.add_column("Git Status", style="bold")
    table.add_column("Last Snapshot", style="blue")

    sorted_repos = sorted(registry.repos.values(), key=lambda r: r.priority, reverse=True)

    async def fetch_last_snapshot_time(repo_id: str, db_path: str) -> str:
        try:
            # Ensure DB exists/tables created (might be overkill to init every time but safe)
            await init_db(db_path)
            async for session in get_session(db_path):
                # This query might need optimization or index, selecting latest by timestamp
                stmt = select(ContextSnapshot).where(ContextSnapshot.repo_id == repo_id).order_by(ContextSnapshot.timestamp.desc()).limit(1)
                result = await session.execute(stmt)
                snapshot = result.scalars().first()
                if snapshot:
                    # Simple relative time formatting could be added here
                    return snapshot.timestamp.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Unknown"
        return "Never"

    # We need to run async DB calls. Since Typer is synchronous, we'll use asyncio.run for the batch?
    # Or just run sequentially for now.
    
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

        git_display = f"{status_icon} {status_text}"
        
        # 2. Last Snapshot (Async wrapper)
        last_snap = asyncio.run(fetch_last_snapshot_time(repo.id, registry.system.db_path))

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
    registry = load_registry()
    console.print("[bold]Prime Directive Doctor[/bold]")
    
    checks = []
    
    # 1. Tmux
    tmux_path = shutil.which("tmux")
    checks.append(("Tmux Installed", "✅" if tmux_path else "❌", tmux_path or "Not found"))

    # 2. Editor
    editor_cmd = registry.system.editor_cmd
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
            target_model = registry.system.ai_model
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
    for repo in registry.repos.values():
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

if __name__ == "__main__":
    app()
