"""MindMap Live — FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv

# Load .env before any module reads os.environ (e.g. db.database on import).
load_dotenv()

import os

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from db.database import engine, AsyncSessionLocal
from routers import edges, nodes, users


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Verify database connectivity on startup; dispose the engine on shutdown."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    yield
    await engine.dispose()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MindMap Live API",
    description="Real-time collaborative knowledge graph builder",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────────
# FRONTEND_ORIGIN accepts a comma-separated list for multi-origin setups,
# e.g. "http://localhost:5173,https://mindmaplive.example.com"

_raw_origins = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Map Python ValueError to HTTP 400 Bad Request."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
# NOTE: These scaffold routers use synchronous Sessions and must be migrated
# to AsyncSession before they will function correctly with the async DB layer.
# New routers should use `AsyncSession = Depends(get_db)` from db.database.

app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])
app.include_router(edges.router, prefix="/api/edges", tags=["edges"])
app.include_router(users.router, prefix="/api/users", tags=["users"])

# Routers to be implemented (uncomment as each is created):
# from routers import auth, maps
# app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
# app.include_router(maps.router, prefix="/api/maps", tags=["maps"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health_check() -> dict[str, str]:
    """Return liveness status and confirm database connectivity.

    Returns HTTP 200 if the service is up and PostgreSQL is reachable.
    A 500 from this endpoint means the DB connection is broken.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
