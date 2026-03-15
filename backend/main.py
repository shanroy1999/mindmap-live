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
from routers import ai, auth, edges, mindmaps, nodes, users, websocket


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Verify database connectivity on startup; dispose the engine on shutdown.

    Redis is intentionally NOT checked here.  The ConnectionManager connects
    to Redis lazily — only when the first WebSocket client broadcasts a message
    or subscribes to a room.  This keeps AI and REST endpoints unaffected by
    Redis availability.
    """
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
# Hard-coded baseline origins (always allowed).
_BASE_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://mindmap-live.vercel.app",
]

# CORS_ORIGINS: optional comma-separated list for runtime overrides, e.g.
#   CORS_ORIGINS="https://staging.example.com,https://preview.example.com"
# FRONTEND_ORIGIN is kept for backwards compatibility.
_extra = os.environ.get("CORS_ORIGINS", os.environ.get("FRONTEND_ORIGIN", ""))
_extra_origins = [o.strip() for o in _extra.split(",") if o.strip()]

_allowed_origins = list(dict.fromkeys(_BASE_ORIGINS + _extra_origins))

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

app.include_router(auth.router,     prefix="/api/auth",     tags=["auth"])
app.include_router(mindmaps.router, prefix="/api/mindmaps", tags=["mindmaps"])
app.include_router(ai.router,       prefix="/api/mindmaps", tags=["ai"])
app.include_router(nodes.router,    prefix="/api/nodes",    tags=["nodes"])
app.include_router(edges.router,    prefix="/api/edges",    tags=["edges"])
app.include_router(users.router,    prefix="/api/users",    tags=["users"])
app.include_router(websocket.router, prefix="/ws",           tags=["websocket"])


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
