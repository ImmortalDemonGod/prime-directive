import pytest
import pytest_asyncio
from sqlmodel import select
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from prime_directive.core.db import (
    Repository,
    ContextSnapshot,
    EventLog,
    EventType,
    AIUsageLog,
    init_db,
    get_session,
    dispose_engine,
)


@pytest_asyncio.fixture
async def async_db_session(tmp_path):
    db_path = tmp_path / "test.db"
    await init_db(str(db_path))

    async for session in get_session(str(db_path)):
        yield session

    # Cleanup (handled by tmp_path usually, but good practice if using engine explicitly)
    await dispose_engine(str(db_path))


@pytest.mark.asyncio
async def test_repository_crud(async_db_session):
    repo = Repository(
        id="test-repo", path="/tmp/test", priority=1, active_branch="main"
    )
    async_db_session.add(repo)
    await async_db_session.commit()
    await async_db_session.refresh(repo)

    result = await async_db_session.execute(
        select(Repository).where(Repository.id == "test-repo")
    )
    fetched_repo = result.scalars().first()

    assert fetched_repo is not None
    assert fetched_repo.id == "test-repo"
    assert fetched_repo.path == "/tmp/test"
    assert fetched_repo.active_branch == "main"


@pytest.mark.asyncio
async def test_sqlite_journal_mode_wal(async_db_session):
    result = await async_db_session.execute(text("PRAGMA journal_mode;"))
    mode = result.scalar_one()
    assert str(mode).lower() == "wal"


@pytest.mark.asyncio
async def test_event_log_insert(async_db_session):
    ev = EventLog(repo_id="test-repo", event_type=EventType.SWITCH_IN)
    async_db_session.add(ev)
    await async_db_session.commit()
    await async_db_session.refresh(ev)

    assert ev.id is not None


@pytest.mark.asyncio
async def test_snapshot_creation(async_db_session):
    repo = Repository(
        id="test-repo",
        path="/tmp/test",
        priority=1,
        active_branch="main",
    )
    async_db_session.add(repo)
    await async_db_session.commit()

    snapshot = ContextSnapshot(
        repo_id="test-repo",
        timestamp=datetime.now(timezone.utc),
        git_status_summary="clean",
        terminal_last_command="ls",
        terminal_output_summary="file1 file2",
        ai_sitrep="All good",
    )
    async_db_session.add(snapshot)
    await async_db_session.commit()
    await async_db_session.refresh(snapshot)

    assert snapshot.id is not None

    result = await async_db_session.execute(
        select(ContextSnapshot).where(ContextSnapshot.repo_id == "test-repo")
    )
    fetched_snapshot = result.scalars().first()

    assert fetched_snapshot is not None
    assert fetched_snapshot.git_status_summary == "clean"
    assert isinstance(fetched_snapshot.timestamp, datetime)


@pytest.mark.asyncio
async def test_snapshot_fk_enforced(async_db_session):
    snapshot = ContextSnapshot(
        repo_id="missing-repo",
        timestamp=datetime.now(timezone.utc),
        git_status_summary="clean",
        terminal_last_command="ls",
        terminal_output_summary="file1 file2",
        ai_sitrep="All good",
    )
    async_db_session.add(snapshot)
    with pytest.raises(IntegrityError):
        await async_db_session.commit()


@pytest.mark.asyncio
async def test_ai_usage_log_insert(async_db_session):
    """Test AIUsageLog table for tracking AI provider usage."""
    usage = AIUsageLog(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        cost_estimate_usd=0.0001,
        success=True,
        repo_id="test-repo",
    )
    async_db_session.add(usage)
    await async_db_session.commit()
    await async_db_session.refresh(usage)

    assert usage.id is not None
    assert usage.provider == "openai"
    assert usage.cost_estimate_usd == 0.0001

    # Query back
    result = await async_db_session.execute(
        select(AIUsageLog).where(AIUsageLog.provider == "openai")
    )
    fetched = result.scalars().first()
    assert fetched is not None
    assert fetched.model == "gpt-4o-mini"
