from datetime import datetime, timezone
from typing import Optional, Dict
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Index, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker

# Define Models
class Repository(SQLModel, table=True):
    id: str = Field(primary_key=True)
    path: str
    priority: int
    active_branch: Optional[str] = None
    last_snapshot_id: Optional[int] = Field(default=None)

    snapshots: list["ContextSnapshot"] = Relationship(back_populates="repo")

class ContextSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: str = Field(foreign_key="repository.id", index=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    git_status_summary: str
    terminal_last_command: str
    terminal_output_summary: str
    ai_sitrep: str

    repo: Optional[Repository] = Relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_contextsnapshot_repo_id_timestamp", "repo_id", "timestamp"),
    )

# Database Connection
# We will use a function to initialize the engine to allow for configuration
_async_engines: Dict[str, AsyncEngine] = {}

def get_engine(db_path: str = "data/prime.db"):
    global _async_engines
    if db_path in _async_engines:
        return _async_engines[db_path]
    
    # Ensure directory exists
    import os
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
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _async_engines[db_path] = engine
    return engine

async def init_db(db_path: str = "data/prime.db"):
    engine = get_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session(db_path: str = "data/prime.db"):
    engine = get_engine(db_path)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

async def dispose_engine(db_path: Optional[str] = None):
    """Dispose cached async engine(s) to ensure clean exit."""
    global _async_engines
    if db_path is not None:
        engine = _async_engines.pop(db_path, None)
        if engine is not None:
            await engine.dispose()
        return

    engines = list(_async_engines.values())
    _async_engines = {}
    for engine in engines:
        await engine.dispose()
