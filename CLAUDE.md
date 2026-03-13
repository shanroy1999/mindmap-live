# MindMap Live — Claude Code Guide

## Project Overview

MindMap Live is a real-time collaborative knowledge graph builder. Users can create, edit, and explore interconnected nodes and edges on a shared canvas, with changes synced instantly across all connected clients. The platform integrates Claude AI to assist with knowledge organization, auto-linking related concepts, and generating graph suggestions.

## Tech Stack

- **Backend**: Python FastAPI
- **Frontend**: React with TypeScript
- **Database**: PostgreSQL
- **Real-time sync**: WebSockets
- **AI features**: Claude API (Anthropic)

## Architecture Overview

This is a monorepo with two top-level packages:

```
mindmap-live/
├── backend/    # FastAPI application (API routes, WebSocket handlers, DB models)
└── frontend/   # React TypeScript application (UI, canvas, real-time client)
```

The backend exposes a REST API for CRUD operations and a WebSocket endpoint for real-time collaboration. The frontend connects to both and renders the interactive graph canvas.

## Coding Standards

### Python (backend)
- Use type hints on all function signatures and variables
- Write docstrings for all functions, classes, and modules (Google style)
- Follow REST conventions for route naming (`GET /nodes`, `POST /nodes`, `PATCH /nodes/{id}`, etc.)
- Use Pydantic models for request/response validation
- Organize routes into routers by domain (e.g., `nodes`, `edges`, `users`)

### TypeScript (frontend)
- Enable and maintain `strict` mode in `tsconfig.json`
- Define explicit types/interfaces for all props, state, and API responses — avoid `any`
- Co-locate component types with their components
- Use named exports over default exports for better refactoring support

## Key Constraints

- **No hardcoded secrets**: All credentials, API keys, and sensitive config must come from environment variables. Use `.env` files locally and never commit them.
- **Error handling required**: Every API endpoint must handle errors explicitly and return appropriate HTTP status codes with descriptive error messages.
- **Environment parity**: Keep `.env.example` files up to date in both `backend/` and `frontend/` so new contributors know what variables are required.
