from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Define Models
class Repository(SQLModel, table=True):
    id: str = Field(primary_key=True)
    path: str
    priority: int
    active_branch: Optional[str] = None
    last_snapshot_id: Optional[int] = Field(default=None)

class ContextSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: str = Field(index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    git_status_summary: str
    terminal_last_command: str
    terminal_output_summary: str
    ai_sitrep: str

# Database Connection
# We will use a function to initialize the engine to allow for configuration
_async_engine = None

def get_engine(db_path: str = "data/prime.db"):
    global _async_engine
    if _async_engine:
        return _async_engine
    
    # Ensure directory exists
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    database_url = f"sqlite+aiosqlite:///{db_path}"
    _async_engine = create_async_engine(database_url, echo=False, connect_args={"check_same_thread": False})
    return _async_engine

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
