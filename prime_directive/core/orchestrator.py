import os
import logging
from typing import Any, Callable, Optional, cast
import asyncio

from sqlalchemy import select

from prime_directive.core.db import ContextSnapshot


def _is_path_prefix(prefix: str, path: str) -> bool:
    """Return True if `prefix` is a directory-prefix of `path`.

    This is path boundary safe.
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
    launch_editor_fn: Callable[[str, str], Any],
    init_db_fn: Callable[[str], Any],
    get_session_fn: Callable[[str], Any],
    dispose_engine_fn: Callable[..., Any],
    console: Any,
    logger: logging.Logger,
) -> bool:
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
        return True

    return False
