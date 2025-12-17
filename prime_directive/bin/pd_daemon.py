import time
import os
import typer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from rich.console import Console
import asyncio
from datetime import datetime
from prime_directive.bin.pd import freeze_logic, load_config
from prime_directive.core.db import dispose_engine

app = typer.Typer()
console = Console()


class AutoFreezeHandler(FileSystemEventHandler):
    def __init__(self, repo_id: str, cfg):
        """
        Initialize the handler with a repository identifier and configuration, and set up its activity-tracking state.
        
        Parameters:
        	repo_id (str): Unique identifier for the repository being monitored.
        	cfg: Configuration object for the repository monitoring and freeze logic.
        
        Attributes:
        	last_modified (datetime): Timestamp of the most recent filesystem activity; initialized to the current time.
        	is_frozen (bool): Whether the repository is currently considered frozen; initialized to False.
        """
        self.repo_id = repo_id
        self.cfg = cfg
        self.last_modified = datetime.now()
        self.is_frozen = False

    def on_any_event(self, event):
        """
        Handle a filesystem event by recording recent activity and clearing the frozen flag for the repository.
        
        Parameters:
            event: The filesystem event object received from watchdog. Directory events are ignored; for other events this updates `last_modified` to the current time and sets `is_frozen` to False if it was True.
        """
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
    Run a background daemon that monitors configured repositories and automatically freezes their context after a period of inactivity.
    
    Parameters:
        interval (int): Seconds between inactivity checks.
        inactivity_limit (int): Inactivity threshold in seconds after which a repository will be frozen.
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
        """
        Execute the freeze logic for a repository and ensure the database engine is disposed afterwards.
        
        Parameters:
            repo_id: Identifier of the repository to freeze.
            cfg: Configuration object used by the freeze logic.
        """
        try:
            await freeze_logic(repo_id, cfg)
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