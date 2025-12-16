import time
import os
import typer
import subprocess
import shutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from rich.console import Console
import asyncio
from datetime import datetime
from prime_directive.bin.pd import freeze_logic, load_config
from prime_directive.core.db import dispose_engine

app = typer.Typer()
console = Console()


def _is_ide_environment() -> bool:
    term_program = (os.environ.get("TERM_PROGRAM") or "").lower()
    if os.environ.get("VSCODE"):
        return True
    if "vscode" in term_program or "windsurf" in term_program:
        return True
    return False


def _tmux_session_has_active_clients(session_name: str) -> bool:
    if not shutil.which("tmux"):
        return False

    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return False

    if result.returncode != 0:
        return False

    try:
        clients = subprocess.run(
            ["tmux", "list-clients", "-t", session_name],
            capture_output=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return False

    if clients.returncode != 0:
        return False

    return bool(clients.stdout.strip())


def _should_skip_terminal_capture(repo_id: str) -> bool:
    if _is_ide_environment():
        return True

    session_name = f"pd-{repo_id}"
    return not _tmux_session_has_active_clients(session_name)


class AutoFreezeHandler(FileSystemEventHandler):
    def __init__(self, repo_id: str, cfg):
        self.repo_id = repo_id
        self.cfg = cfg
        self.last_modified = datetime.now()
        self.is_frozen = False

    def on_any_event(self, event):
        if event.is_directory:
            return
        # Activity detected, reset state
        self.last_modified = datetime.now()
        if self.is_frozen:
            # console.print(
            #     f"[green]Activity detected in {self.repo_id}. "
            #     "Unfreezing state...[/green]"
            # )
            self.is_frozen = False


@app.command()
def main(
    interval: int = typer.Option(
        300,
        help="Check interval in seconds",
    ),
    inactivity_limit: int = typer.Option(
        1800,
        help="Inactivity limit in seconds (30 min)",
    ),
):
    """
    Background daemon to monitor repositories and auto-freeze context on
    inactivity.
    """
    msg = "[bold green]Starting Prime Directive Daemon...[/bold green]"
    console.print(msg)
    cfg = load_config()
    observer = Observer()
    handlers = {}

    for repo_id, repo_config in cfg.repos.items():
        if os.path.exists(repo_config.path):
            console.print(f"Monitoring {repo_id} at {repo_config.path}")
            handler = AutoFreezeHandler(repo_id, cfg)
            handlers[repo_id] = handler
            observer.schedule(handler, repo_config.path, recursive=True)
        else:
            console.print(
                f"[yellow]Skipping {repo_id}: Path not found[/yellow]"
            )

    observer.start()

    async def run_freeze(repo_id, cfg):
        try:
            skip_terminal_capture = _should_skip_terminal_capture(repo_id)
            if skip_terminal_capture:
                console.print(
                    f"[yellow]Skipping terminal capture for {repo_id}[/yellow]"
                )
            await freeze_logic(
                repo_id,
                cfg,
                skip_terminal_capture=skip_terminal_capture,
            )
        finally:
            await dispose_engine()

    try:
        while True:
            time.sleep(interval)
            now = datetime.now()
            for repo_id, handler in handlers.items():
                # Check inactivity
                delta = now - handler.last_modified
                if (
                    delta.total_seconds() > inactivity_limit
                    and not handler.is_frozen
                ):
                    console.print(
                        f"[blue]Inactivity detected in {repo_id} ({delta}). "
                        "Freezing...[/blue]"
                    )
                    try:
                        asyncio.run(run_freeze(repo_id, cfg))
                        handler.is_frozen = True
                        console.print(
                            f"[green]Repository {repo_id} is now "
                            "FROZEN.[/green]"
                        )
                    except (OSError, ValueError) as e:
                        console.print(
                            f"[red]Error freezing {repo_id}: {e}[/red]"
                        )

    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer.join()


if __name__ == "__main__":
    app()
