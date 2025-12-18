import os
import logging
from typing import Any, Callable, Optional, cast
import asyncio

from sqlalchemy import select

from prime_directive.core.db import ContextSnapshot, EventLog, EventType


def _is_path_prefix(prefix: str, path: str) -> bool:
    """
    Determine whether `prefix` is a directory path prefix of `path`.

    Paths are normalized and resolved to absolute paths; equality counts as a
    match.
    Only directory-boundary prefixes are considered.
    For example, '/a/b' matches '/a/b/c' but not '/a/bc'.

    Returns:
        bool: `True` if `prefix` is equal to `path` or is a directory-prefix of
            `path`, `False` otherwise.
    """
    prefix_norm = os.path.normpath(os.path.abspath(prefix))
    path_norm = os.path.normpath(os.path.abspath(path))

    if path_norm == prefix_norm:
        return True

    return path_norm.startswith(prefix_norm + os.sep)


def detect_current_repo_id(cwd: str, repos: Any) -> Optional[str]:
    """Detect current repo by longest matching repo path prefix."""
    best_repo_id: Optional[str] = None
    best_len = -1

    for repo_id, repo_cfg in repos.items():
        repo_path = getattr(repo_cfg, "path", None) or repo_cfg.get("path")
        if not repo_path:
            continue

        if _is_path_prefix(repo_path, cwd):
            repo_path_norm = os.path.normpath(os.path.abspath(repo_path))
            if len(repo_path_norm) > best_len:
                best_len = len(repo_path_norm)
                best_repo_id = repo_id

    return best_repo_id


async def switch_logic(
    target_repo_id: str,
    cfg: Any,
    *,
    cwd: str,
    freeze_fn: Callable[[str, Any], Any],
    ensure_session_fn: Callable[..., Any],
    launch_editor_fn: Callable[[str, str, list[str]], Any],
    init_db_fn: Callable[[str], Any],
    get_session_fn: Callable[[str], Any],
    dispose_engine_fn: Callable[..., Any],
    console: Any,
    logger: logging.Logger,
) -> None:
    """
    Switch the active workspace to the repository identified by `target_repo_id`.
    
    Detects the current repository based on `cwd` and, if different, attempts to freeze it.
    Ensures a session for the target repository and launches the editor unless `cfg.system.mock_mode` is true (in mock mode these actions are logged).
    Initializes the database, records an `EventType.SWITCH_IN` event for the target repository, and prints the most recent `ContextSnapshot` (human note, AI summary, and timestamp) if one exists.
    Always disposes database engine resources via `dispose_engine_fn()`.
    
    Parameters:
        target_repo_id (str): Identifier of the repository to switch to.
        cfg (Any): Configuration object exposing `repos` (mapping of repo id to repo config) and `system` with `mock_mode`, `editor_cmd`, optional `editor_args`, and `db_path`.
        cwd (str): Current working directory used to detect the active repository.
        freeze_fn (Callable[[str, Any], Any]): Async callable to freeze a repository given its id and the configuration.
        ensure_session_fn (Callable[..., Any]): Callable to ensure or create a session for the target repository.
        launch_editor_fn (Callable[[str, str, list[str]], Any]): Callable to launch the editor for a path with command and argument list.
        init_db_fn (Callable[[str], Any]): Async callable to initialize or connect to the database at the given path.
        get_session_fn (Callable[[str], Any]): Callable that yields async DB session objects for the given DB path.
        dispose_engine_fn (Callable[..., Any]): Async callable to dispose/cleanup DB engine and related resources.
        console (Any): Console-like object used for user-facing prints.
        logger (logging.Logger): Logger for informational messages.
    """
    try:
        current_repo_id = detect_current_repo_id(cwd, cfg.repos)

        if current_repo_id and current_repo_id != target_repo_id:
            console.print(
                f"[yellow]Detected current repo: {current_repo_id}[/yellow]"
            )
            logger.info(f"Auto-freezing current repo: {current_repo_id}")
            try:
                await freeze_fn(current_repo_id, cfg)
            except Exception as e:
                console.print(
                    f"[red]Failed to freeze {current_repo_id}: {e}[/red]"
                )

        target_repo = cfg.repos[target_repo_id]
        target_path = target_repo.path

        console.print(
            f"[bold green]>>> WARPING TO {target_repo_id.upper()} >>>"
            "[/bold green]"
        )
        logger.info(f"Switching to {target_repo_id}")

        if cfg.system.mock_mode:
            logger.info(f"MOCK MODE: ensure_session({target_repo_id})")
            logger.info(f"MOCK MODE: launch_editor({target_path})")
        else:
            ensure_session_fn(target_repo_id, target_path, attach=False)
            editor_args = getattr(cfg.system, "editor_args", ["-n"])
            launch_editor_fn(target_path, cfg.system.editor_cmd, editor_args)

        await init_db_fn(cfg.system.db_path)
        async for session in get_session_fn(cfg.system.db_path):
            session.add(
                EventLog(
                    repo_id=target_repo_id,
                    event_type=EventType.SWITCH_IN,
                )
            )
            await session.commit()

            repo_id_col = cast(Any, ContextSnapshot.repo_id)
            ts_col = cast(Any, ContextSnapshot.timestamp)
            stmt = (
                select(ContextSnapshot)
                .where(repo_id_col == target_repo_id)
                .order_by(ts_col.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            snapshot = result.scalars().first()

            console.print("\n[bold reverse] SITREP [/bold reverse]")
            if snapshot:
                if snapshot.human_note:
                    console.print(
                        "[bold magenta]>>> HUMAN NOTE:[/bold magenta] "
                        f"{snapshot.human_note}"
                    )
                console.print(
                    "[bold cyan]>>> AI SUMMARY:[/bold cyan] "
                    f"{snapshot.ai_sitrep}"
                )
                console.print(
                    "[bold yellow]>>> TIMESTAMP:[/bold yellow] "
                    f"{snapshot.timestamp}"
                )
            else:
                console.print("[italic]No previous snapshot found.[/italic]")
    finally:
        await dispose_engine_fn()


def run_switch(
    target_repo_id: str,
    cfg: Any,
    *,
    cwd: str,
    freeze_fn: Callable[[str, Any], Any],
    ensure_session_fn: Callable[..., Any],
    launch_editor_fn: Callable[[str, str, list[str]], Any],
    init_db_fn: Callable[[str], Any],
    get_session_fn: Callable[[str], Any],
    dispose_engine_fn: Callable[..., Any],
    console: Any,
    logger: logging.Logger,
) -> bool:
    """
    Execute the repository switch workflow and determine if a normal session
    should proceed.

    Runs the asynchronous switch_logic synchronously and performs cleanup;
    after completion, returns whether the caller should proceed with a normal
    (non-mock, non-TMUX) session.

    Parameters:
        target_repo_id (str): Identifier of the repository to switch into.
        cfg (Any): Configuration object containing repository and system
            settings (expects cfg.repos and cfg.system.mock_mode/editor_cmd/
            editor_args/db_path).
        cwd (str): Current working directory used to detect the active
            repository.
        freeze_fn (Callable[[str, Any], Any]): Function to freeze a repository
            state;
            called with the current repository id and its config.
        ensure_session_fn (Callable[..., Any]): Function that ensures a session
            exists for the target repository.
        launch_editor_fn (Callable[[str, str, list[str]], Any]): Function to
            launch an editor given a path, editor command, and editor
            arguments.
        init_db_fn (Callable[[str], Any]): Function to initialize or open the
            database at the given path.
        get_session_fn (Callable[[str], Any]): Callable that yields database
            sessions for a given DB path.
        dispose_engine_fn (Callable[..., Any]): Cleanup function invoked after
            switch_logic completes.
        console (Any): Console-like object used for user-facing output.
        logger (logging.Logger): Logger for diagnostic messages.

    Returns:
        True if cfg.system.mock_mode is false and the TMUX environment variable
        is not set, False otherwise.
    """
    asyncio.run(
        switch_logic(
            target_repo_id,
            cfg,
            cwd=cwd,
            freeze_fn=freeze_fn,
            ensure_session_fn=ensure_session_fn,
            launch_editor_fn=launch_editor_fn,
            init_db_fn=init_db_fn,
            get_session_fn=get_session_fn,
            dispose_engine_fn=dispose_engine_fn,
            console=console,
            logger=logger,
        )
    )

    if (
        not cfg.system.mock_mode
        and not os.environ.get("TMUX")
    ):
        return True

    return False