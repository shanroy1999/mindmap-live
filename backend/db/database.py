"""Async database engine, session factory, and declarative base.

Uses SQLAlchemy 2 async API with asyncpg as the PostgreSQL driver.
DATABASE_URL must use the postgresql+asyncpg:// scheme.
"""

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models.

    AsyncAttrs enables awaitable access to lazy-loaded relationships
    (e.g. ``await node.awaitable_attrs.map``).
    """


def _build_engine():
    """Create the async SQLAlchemy engine from DATABASE_URL.

    Automatically upgrades a bare postgresql:// URL to
    postgresql+asyncpg:// so plain Postgres connection strings work
    without modification.
    """
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        # Heroku / Railway emit postgres:// — normalise it too
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        url,
        pool_pre_ping=True,   # discard stale connections before use
        pool_size=10,
        max_overflow=20,
        echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
    )


engine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,  # keep attributes accessible after commit
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session and ensure it is closed after use.

    Rolls back automatically on any unhandled exception so the connection
    is returned to the pool in a clean state.

    Intended for use as a FastAPI dependency::

        async def my_route(db: AsyncSession = Depends(get_db)) -> ...:
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
