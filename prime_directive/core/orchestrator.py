import os
import logging
from typing import Any, Callable, Optional, cast
import asyncio

from sqlalchemy import select

from prime_directive.core.db import ContextSnapshot


def _is_path_prefix(prefix: str, path: str) -> bool:
    """
    Determine whether `prefix` is a directory-path prefix of `path`, respecting path boundaries.
    
    Returns:
        bool: `True` if `path` equals `prefix` or is located inside `prefix` (i.e., begins with `prefix` followed by a path separator), `False` otherwise.
    """
    prefix_norm = os.path.normpath(os.path.abspath(prefix))
    path_norm = os.path.normpath(os.path.abspath(path))

    if path_norm == prefix_norm:
        return True

    return path_norm.startswith(prefix_norm + os.sep)


def detect_current_repo_id(cwd: str, repos: Any) -> Optional[str]:
    """
    Detect which repository (by repo_id) contains the given working directory by selecting the repo whose configured path is the longest path-prefix of cwd.
    
    Parameters:
        cwd (str): Current working directory path to test.
        repos (Any): Mapping of repo_id to repository configuration objects or dicts; each config must expose a `path` attribute or key.
    
    Returns:
        Optional[str]: The repo_id whose path is the longest matching prefix of `cwd`, or `None` if no repository matches.
    """
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
    launch_editor_fn: Callable[[str, str], Any],
    init_db_fn: Callable[[str], Any],
    get_session_fn: Callable[[str], Any],
    dispose_engine_fn: Callable[..., Any],
    console: Any,
    logger: logging.Logger,
) -> None:
    """
    Coordinate switching the working context to the specified repository and print a situational report.
    
    Detects the repository containing `cwd` and, if different from `target_repo_id`, attempts to freeze the current repository via `freeze_fn`. Ensures a session and optionally launches the editor for the target repository (mock behavior when `cfg.system.mock_mode` is true), initializes the database, retrieves the latest ContextSnapshot for the target repository, and prints a SITREP with any human note, AI summary, and timestamp. Always disposes engine resources by calling `dispose_engine_fn`.
    
    Parameters:
        target_repo_id (str): Identifier of the repository to switch to.
        cfg (Any): Configuration object containing `repos` mapping and `system` settings (`mock_mode`, `editor_cmd`, `db_path`).
        cwd (str): Current working directory used to detect the active repository.
        freeze_fn (Callable[[str, Any], Any]): Callable invoked with (repo_id, cfg) to freeze the given repository; exceptions from this call are caught and reported to `console`.
        ensure_session_fn (Callable[..., Any]): Callable to ensure or create a session for a repo; called as ensure_session_fn(target_repo_id, target_path, attach=False) in non-mock mode and called again after switch by the runner when appropriate.
        launch_editor_fn (Callable[[str, str], Any]): Callable to launch the editor; called with (path, editor_cmd) in non-mock mode.
        init_db_fn (Callable[[str], Any]): Callable invoked with the database path to initialize the DB layer before querying snapshots.
        get_session_fn (Callable[[str], Any]): Callable that yields database sessions for the given DB path; used to execute a query for the most recent ContextSnapshot for `target_repo_id`.
        dispose_engine_fn (Callable[..., Any]): Callable invoked (awaited) unconditionally at the end to dispose DB/engine resources.
        console (Any): Console-like object used to print user-facing messages and SITREP output.
        logger (logging.Logger): Logger used to record informational events and debug messages.
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
            launch_editor_fn(target_path, cfg.system.editor_cmd)

        await init_db_fn(cfg.system.db_path)
        async for session in get_session_fn(cfg.system.db_path):
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
    launch_editor_fn: Callable[[str, str], Any],
    init_db_fn: Callable[[str], Any],
    get_session_fn: Callable[[str], Any],
    dispose_engine_fn: Callable[..., Any],
    console: Any,
    logger: logging.Logger,
) -> None:

    """
    Synchronously run the repository switch workflow and, when appropriate, ensure a session is attached for the target repository.
    
    Runs the asynchronous switch_logic workflow for the specified target repository using the provided configuration and helper functions. After the workflow completes, if the configuration is not in mock mode and the process is not running inside a TMUX session, calls ensure_session_fn with the target repository id and the repository's configured path to establish/attach a session.
    
    Parameters:
        target_repo_id (str): Identifier of the repository to switch to.
        cfg (Any): Configuration object containing a `repos` mapping and `system` settings (including `mock_mode` and repo paths).
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

    if (not cfg.system.mock_mode) and (not os.environ.get("TMUX")):
        target_path = cfg.repos[target_repo_id].path
        ensure_session_fn(target_repo_id, target_path)