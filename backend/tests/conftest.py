"""Shared pytest fixtures for the MindMap Live backend test suite.

Database strategy
-----------------
* Schema creation/teardown happens **once per session** via a synchronous
  ``setup_test_schema`` fixture that calls ``asyncio.run()`` — this avoids
  event-loop conflicts with pytest-asyncio's function-scoped loops.
* Each test function gets its own ``AsyncSession`` wrapped in a SAVEPOINT
  transaction (``join_transaction_mode="create_savepoint"``).  When the test
  finishes the outer connection is rolled back, leaving the schema clean for
  the next test without re-running DDL.

HTTP client strategy
--------------------
* ``async_client`` replaces the production lifespan with a no-op and overrides
  ``get_db`` so route handlers use the same savepoint session as the test.
* It also patches ``main.AsyncSessionLocal`` so the ``/health`` endpoint (which
  calls it directly) also uses the test session.
* ``failing_client`` patches ``AsyncSessionLocal`` with a mock that raises
  ``OperationalError``, letting us test the DB-unreachable path without
  terminating a real connection.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Register all models with Base.metadata before any DDL.
import models.graph  # noqa: F401
from db.database import Base, get_db
from main import app
from models.graph import Edge, MapMember, MapRole, MindMap, Node, User


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalise_url(raw: str) -> str:
    """Upgrade a plain postgres:// URL to postgresql+asyncpg:// for asyncpg."""
    for prefix, replacement in [
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ]:
        if raw.startswith(prefix):
            return raw.replace(prefix, replacement, 1)
    return raw


def _get_test_db_url() -> str:
    """Return the test database URL from the environment."""
    raw = os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get("DATABASE_URL", ""),
    )
    return _normalise_url(raw) if raw else ""


TEST_DB_URL = _get_test_db_url()


# ── Session-scoped event loop (shared by all async fixtures) ──────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Provide a single event loop for the entire test session.

    This allows session-scoped async fixtures (``test_engine``) and
    function-scoped ones (``db_session``) to share the same loop without
    SQLAlchemy connection-pool affinity errors.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Schema setup / teardown (sync, session-scoped) ───────────────────────────


@pytest.fixture(scope="session", autouse=True)
def setup_test_schema():
    """Create the full database schema once before any test runs.

    Uses ``asyncio.run()`` (its own loop, separate from the pytest-asyncio
    session loop) so that it never conflicts with running tests.

    Skips the entire session if no database URL is configured.
    """
    if not TEST_DB_URL:
        pytest.skip(
            "No database URL configured for tests. "
            "Set TEST_DATABASE_URL or DATABASE_URL."
        )

    async def _create() -> None:
        engine = create_async_engine(TEST_DB_URL, echo=False)
        async with engine.begin() as conn:
            # Drop first for a clean slate (handles leftover state from a
            # previously aborted session).
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    yield

    async def _drop() -> None:
        engine = create_async_engine(TEST_DB_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_drop())


# ── Per-test database session (function-scoped, transaction rollback) ─────────


@pytest_asyncio.fixture
async def db_session(setup_test_schema) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession isolated inside a SAVEPOINT transaction.

    Every ORM write during the test (``flush``, ``commit``) operates against
    a SAVEPOINT rather than the real transaction, so rolling back the outer
    connection after the test leaves the database unchanged.

    After an ``IntegrityError``, call ``await db_session.rollback()`` inside
    the test to recover the session before making further assertions.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
    await engine.dispose()


# ── Null lifespan helper ──────────────────────────────────────────────────────


@asynccontextmanager
async def _null_lifespan(app_: Any) -> AsyncGenerator[None, None]:
    """No-op lifespan that skips the production DB connectivity check."""
    yield


# ── HTTP test clients ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX AsyncClient wired to the test database.

    * The production lifespan is replaced with a no-op.
    * ``get_db`` is overridden so route handlers use ``db_session``.
    * ``main.AsyncSessionLocal`` is replaced with a factory that also yields
      ``db_session``, so ``/health`` (which calls it directly) works correctly.
    """
    import main as _main

    # Wrap db_session as an async context manager for AsyncSessionLocal callers.
    @asynccontextmanager
    async def _session_ctx() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    class _FakeSessionLocal:
        def __call__(self) -> Any:
            return _session_ctx()

    # Override get_db for dependency-injected route handlers.
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    original_lifespan = app.router.lifespan_context
    original_asl = _main.AsyncSessionLocal

    app.router.lifespan_context = _null_lifespan
    _main.AsyncSessionLocal = _FakeSessionLocal()
    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    # Always restore — even if the test raised.
    app.router.lifespan_context = original_lifespan
    _main.AsyncSessionLocal = original_asl
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def failing_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTPX AsyncClient where ``AsyncSessionLocal`` raises ``OperationalError``.

    Used to test how endpoints behave when the database is unreachable.
    ``raise_server_exceptions=False`` is set so the 500 response is captured
    as an HTTP response object rather than re-raised.
    """
    import main as _main

    mock_session = AsyncMock()
    mock_session.execute.side_effect = OperationalError(
        "connection refused", {}, Exception("conn refused")
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    class _FailingSessionLocal:
        def __call__(self) -> Any:
            return mock_session

    original_lifespan = app.router.lifespan_context
    original_asl = _main.AsyncSessionLocal

    app.router.lifespan_context = _null_lifespan
    _main.AsyncSessionLocal = _FailingSessionLocal()

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client

    app.router.lifespan_context = original_lifespan
    _main.AsyncSessionLocal = original_asl


# ── Data factories ────────────────────────────────────────────────────────────
# Each factory is a regular fixture that returns an async callable.  Tests call
# it like: ``user = await make_user()`` or ``user = await make_user(email="x")``.
# All factories flush (not commit) so data is visible within the current
# savepoint but never durably written to the database.


@pytest.fixture
def make_user(db_session: AsyncSession):
    """Factory for creating persisted ``User`` rows."""

    async def factory(
        email: str = "alice@example.com",
        display_name: str = "Alice",
        hashed_password: str = "hashed_password_value",
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email,
            display_name=display_name,
            hashed_password=hashed_password,
            is_active=is_active,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return factory


@pytest.fixture
def make_map(db_session: AsyncSession):
    """Factory for creating persisted ``MindMap`` rows."""

    async def factory(
        owner: User,
        title: str = "Test Map",
        description: Optional[str] = None,
        is_public: bool = False,
    ) -> MindMap:
        mindmap = MindMap(
            owner_id=owner.id,
            title=title,
            description=description,
            is_public=is_public,
        )
        db_session.add(mindmap)
        await db_session.flush()
        return mindmap

    return factory


@pytest.fixture
def make_node(db_session: AsyncSession):
    """Factory for creating persisted ``Node`` rows."""

    async def factory(
        mindmap: MindMap,
        label: str = "Concept A",
        description: Optional[str] = None,
        color: str = "#6366f1",
        x: float = 0.0,
        y: float = 0.0,
        created_by: Optional[User] = None,
    ) -> Node:
        node = Node(
            map_id=mindmap.id,
            label=label,
            description=description,
            color=color,
            x=x,
            y=y,
            created_by=created_by.id if created_by else None,
        )
        db_session.add(node)
        await db_session.flush()
        return node

    return factory


@pytest.fixture
def make_edge(db_session: AsyncSession):
    """Factory for creating persisted ``Edge`` rows."""

    async def factory(
        mindmap: MindMap,
        source: Node,
        target: Node,
        label: Optional[str] = None,
        created_by: Optional[User] = None,
    ) -> Edge:
        edge = Edge(
            map_id=mindmap.id,
            source_id=source.id,
            target_id=target.id,
            label=label,
            created_by=created_by.id if created_by else None,
        )
        db_session.add(edge)
        await db_session.flush()
        return edge

    return factory
