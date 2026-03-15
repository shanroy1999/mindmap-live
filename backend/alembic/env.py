"""Alembic environment — runs migrations asynchronously via asyncpg.

Reads DATABASE_URL from the environment (or backend/.env via python-dotenv).
Imports all ORM models so that ``alembic revision --autogenerate`` can diff
the live database schema against the declared SQLAlchemy metadata.

Offline mode (``--sql``) emits raw SQL without connecting to the database.
Online mode connects via asyncpg and applies migrations inside a transaction.
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

# ── Environment setup ──────────────────────────────────────────────────────────

# Load backend/.env so DATABASE_URL is available when running `alembic` from
# the backend/ directory.  The file is two levels up from alembic/env.py.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Ensure backend/ is on sys.path so that `db`, `models`, etc. are importable
# without installing the package.
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# ── Alembic config object ──────────────────────────────────────────────────────

config = context.config

# Initialise Python logging from the [loggers]/[handlers] sections in alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import models so Alembic can autogenerate schema diffs ────────────────────
# db.database must be imported first to define Base before models extend it.
from db.database import Base  # noqa: E402
import models.graph  # noqa: E402, F401  — side-effect: registers all models

target_metadata = Base.metadata


# ── URL helper ─────────────────────────────────────────────────────────────────


def _get_url() -> str:
    """Return a ``postgresql+asyncpg://`` URL from the environment.

    Accepts bare ``postgresql://`` or ``postgres://`` URLs and normalises
    them so they work with SQLAlchemy's asyncpg dialect.
    """
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# ── Offline migrations ─────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Generate a SQL migration script without connecting to the database.

    Useful for reviewing migration SQL before applying it, or for DBAs who
    prefer to apply migrations manually::

        alembic upgrade head --sql > upgrade.sql
    """
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Detect server_default changes during autogenerate.
        compare_server_defaults=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations ──────────────────────────────────────────────────────────


def _do_run_migrations(connection) -> None:
    """Configure context and run migrations on an open synchronous connection.

    Called by ``connection.run_sync()`` from the async driver so that Alembic
    can use its standard synchronous migration API while the underlying
    transport remains asyncpg.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect server_default changes during autogenerate.
        compare_server_defaults=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Create a temporary async engine, connect, and run migrations."""
    engine = create_async_engine(_get_url(), echo=False)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """Apply migrations against a live database using asyncpg."""
    asyncio.run(_run_async_migrations())


# ── Entry point ────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
