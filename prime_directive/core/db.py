import os
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Optional

import sqlalchemy
from sqlalchemy import Index, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import Field, Relationship, SQLModel

# Define Models


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repository(SQLModel, table=True):  # type: ignore[call-arg]
    id: str = Field(primary_key=True)
    path: str
    priority: int
    active_branch: Optional[str] = None
    last_snapshot_id: Optional[int] = Field(default=None)

    snapshots: list["ContextSnapshot"] = Relationship(back_populates="repo")


class ContextSnapshot(SQLModel, table=True):  # type: ignore[call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: str = Field(foreign_key="repository.id", index=True)
    timestamp: datetime = Field(default_factory=_utcnow)
    git_status_summary: str
    terminal_last_command: str
    terminal_output_summary: str
    ai_sitrep: str
    human_note: Optional[str] = Field(default=None)
    human_objective: Optional[str] = Field(default=None)
    human_blocker: Optional[str] = Field(default=None)
    human_next_step: Optional[str] = Field(default=None)

    repo: Optional[Repository] = Relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_contextsnapshot_repo_id_timestamp", "repo_id", "timestamp"),
    )


class EventType(str, Enum):
    SWITCH_IN = "SWITCH_IN"
    COMMIT = "COMMIT"


class EventLog(SQLModel, table=True):  # type: ignore[call-arg]
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=_utcnow)
    repo_id: str = Field(index=True)
    event_type: EventType = Field(index=True)


class AIUsageLog(SQLModel, table=True):  # type: ignore[call-arg]
    """Track AI provider usage for budget enforcement."""

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=_utcnow, index=True)
    provider: str = Field(index=True)  # "ollama" or "openai"
    model: str
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cost_estimate_usd: float = Field(default=0.0)
    success: bool = Field(default=True)
    repo_id: Optional[str] = Field(default=None)


# Database Connection
# We will use a function to initialize the engine to allow for configuration
_engine_lock = threading.Lock()
_async_engines: Dict[str, AsyncEngine] = {}


def get_engine(db_path: str = "~/.prime-directive/data/prime.db"):
    # Expand ~ to home directory
    """
    Provide a cached database engine connected to the SQLite database at the given path.
    
    Parameters:
        db_path (str): Filesystem path for the SQLite database. A leading "~" is
            expanded to the user's home directory. The special value ":memory:"
            uses an in-memory database. Defaults to "~/.prime-directive/data/prime.db".
    
    Returns:
        sqlalchemy.ext.asyncio.AsyncEngine: An AsyncEngine configured for SQLite
            with foreign key enforcement and WAL journaling. The same engine
            instance is returned for repeated calls with the same expanded path.
    
    Notes:
        If `db_path` is not ":memory:", the function ensures the parent directory
        exists before creating the engine. On each new DB-API connection the engine
        sets `PRAGMA foreign_keys=ON` and `PRAGMA journal_mode=WAL`.
    """
    db_path = os.path.expanduser(db_path)

    engine = _async_engines.get(db_path)
    if engine is not None:
        return engine

    with _engine_lock:
        engine = _async_engines.get(db_path)
        if engine is not None:
            return engine

        # Ensure directory exists
        if db_path != ":memory:":
            dir_name = os.path.dirname(db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

        database_url = f"sqlite+aiosqlite:///{db_path}"

        engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            """
            Set SQLite pragmas on a newly opened DB-API connection to enable foreign key enforcement and WAL journaling.

            This function executes PRAGMA statements on the given DB-API
            connection: it enables foreign key constraints ('PRAGMA
            foreign_keys=ON') and sets the journal mode to write-ahead logging
            ('PRAGMA journal_mode=WAL'). It is intended to be used as a
            SQLAlchemy connect event listener.

            Parameters:
                dbapi_connection: The raw DB-API connection object provided
                    by SQLAlchemy on connect.
                _connection_record: Connection record passed by SQLAlchemy
                    (unused).
            """
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        _async_engines[db_path] = engine
        return engine


async def init_db(db_path: str = "data/prime.db") -> None:
    """
    Initialize the database and apply schema migrations up to the current version.
    
    Parameters:
        db_path (str): Filesystem path to the SQLite database file (defaults to "data/prime.db").
    """
    await migrate_db(db_path)


# Schema version history:
#   0 → 1: initial schema (Repository, ContextSnapshot, EventLog, AIUsageLog)
_CURRENT_SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, list[str]] = {
    1: [],  # baseline — tables created by create_all; no ALTER statements needed
}


async def migrate_db(db_path: str = "data/prime.db") -> None:
    """
    Apply any pending SQL schema migrations to the SQLite database at the given path.
    
    This function ensures database tables for the current models exist and then advances the
    database schema version by applying SQL statements listed in the module-level _MIGRATIONS
    mapping for each subsequent version until reaching _CURRENT_SCHEMA_VERSION. It is safe
    to call on every startup because it performs no work when the database is already at
    the current schema version.
    
    Parameters:
        db_path (str): Filesystem path to the SQLite database file (e.g., "data/prime.db").
    """
    engine = get_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

        def _get_version(sync_conn: Any) -> int:
            """
            Read the SQLite `PRAGMA user_version` from a synchronous DB connection and return it as an integer.
            
            Parameters:
                sync_conn (Any): A synchronous DB-API or SQLAlchemy Connection that supports executing SQL and fetching rows.
            
            Returns:
                int: The `user_version` value from the database, or 0 if the query returned no rows.
            """
            row = sync_conn.execute(
                sqlalchemy.text("PRAGMA user_version")
            ).fetchone()
            return int(row[0]) if row else 0

        def _set_version(sync_conn: Any, version: int) -> None:
            """
            Set the SQLite `user_version` PRAGMA to the given integer schema version.
            
            Parameters:
                sync_conn (Any): A synchronous DB-API or SQLAlchemy connection object on which the PRAGMA will be executed.
                version (int): The schema version number to store in `PRAGMA user_version`.
            """
            sync_conn.execute(
                sqlalchemy.text(f"PRAGMA user_version = {version}")
            )

        current = await conn.run_sync(_get_version)

        if current == 0:
            # Fresh database — create_all() already built the full schema,
            # so skip incremental migrations and stamp the current version.
            await conn.run_sync(
                lambda c: _set_version(c, _CURRENT_SCHEMA_VERSION)
            )
        else:
            for version in range(current + 1, _CURRENT_SCHEMA_VERSION + 1):
                statements = _MIGRATIONS.get(version, [])
                for sql in statements:
                    await conn.execute(sqlalchemy.text(sql))
                await conn.run_sync(lambda c, v=version: _set_version(c, v))


async def get_session(
    db_path: str = "data/prime.db",
) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async SQLAlchemy session bound to the configured SQLite database.
    
    Parameters:
        db_path (str): Path to the SQLite database file (tilde `~` is expanded). Defaults to "data/prime.db".
    
    Returns:
        AsyncSession: An open AsyncSession instance bound to the database; the session is closed when the generator exits.
    """
    engine = get_engine(db_path)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def dispose_engine(db_path: Optional[str] = None):
    """Dispose cached async engine(s) to ensure clean exit."""
    global _async_engines
    if db_path is not None:
        with _engine_lock:
            engine = _async_engines.pop(db_path, None)
        if engine is not None:
            await engine.dispose()
        return

    with _engine_lock:
        engines = list(_async_engines.values())
        _async_engines = {}
    for engine in engines:
        await engine.dispose()
