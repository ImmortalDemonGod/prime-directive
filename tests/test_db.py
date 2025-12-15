import pytest
import pytest_asyncio
from sqlmodel import select
from datetime import datetime
from prime_directive.core.db import Repository, ContextSnapshot, init_db, get_session, get_engine
import os

@pytest_asyncio.fixture
async def async_db_session(tmp_path):
    db_path = tmp_path / "test.db"
    await init_db(str(db_path))
    
    async for session in get_session(str(db_path)):
        yield session
    
    # Cleanup (handled by tmp_path usually, but good practice if using engine explicitly)
    engine = get_engine(str(db_path))
    await engine.dispose()

@pytest.mark.asyncio
async def test_repository_crud(async_db_session):
    repo = Repository(
        id="test-repo", 
        path="/tmp/test", 
        priority=1, 
        active_branch="main"
    )
    async_db_session.add(repo)
    await async_db_session.commit()
    await async_db_session.refresh(repo)

    result = await async_db_session.exec(select(Repository).where(Repository.id == "test-repo"))
    fetched_repo = result.first()
    
    assert fetched_repo is not None
    assert fetched_repo.id == "test-repo"
    assert fetched_repo.path == "/tmp/test"
    assert fetched_repo.active_branch == "main"

@pytest.mark.asyncio
async def test_snapshot_creation(async_db_session):
    snapshot = ContextSnapshot(
        repo_id="test-repo",
        timestamp=datetime.utcnow(),
        git_status_summary="clean",
        terminal_last_command="ls",
        terminal_output_summary="file1 file2",
        ai_sitrep="All good"
    )
    async_db_session.add(snapshot)
    await async_db_session.commit()
    await async_db_session.refresh(snapshot)
    
    assert snapshot.id is not None
    
    result = await async_db_session.exec(select(ContextSnapshot).where(ContextSnapshot.repo_id == "test-repo"))
    fetched_snapshot = result.first()
    
    assert fetched_snapshot is not None
    assert fetched_snapshot.git_status_summary == "clean"
    assert isinstance(fetched_snapshot.timestamp, datetime)
