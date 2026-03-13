# MindMap Live

A real-time collaborative knowledge graph builder. Create interconnected idea nodes, draw relationships between them, and let AI suggest connections you haven't thought of — all synced live across multiple users.

## Features

- Real-time multi-user collaboration via WebSockets
- Interactive node/edge canvas with drag-and-drop
- AI-powered relationship suggestions (Claude API)
- Semantic clustering of related nodes via embeddings
- JWT authentication and per-map access control

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 |
| Frontend | React 18, TypeScript (strict), Vite |
| Database | PostgreSQL 15+ |
| Cache / Pub-Sub | Redis 7+ |
| AI | Anthropic Claude API |
| Auth | JWT (python-jose + passlib) |

## Project Structure

```
mindmap-live/
├── backend/
│   ├── db/               # Engine, session factory, declarative Base
│   ├── models/           # SQLAlchemy ORM table definitions
│   ├── schemas/          # Pydantic request/response schemas
│   ├── routers/          # FastAPI route handlers (nodes, edges, users)
│   ├── services/         # Business logic and AI integration
│   ├── tests/            # pytest test suite
│   ├── main.py           # FastAPI app + middleware wiring
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/          # REST API client
│   │   ├── components/   # React components
│   │   ├── hooks/        # Custom React hooks
│   │   └── types/        # Shared TypeScript interfaces
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── .env.example
└── docs/
    └── ARCHITECTURE.md   # System design and key decisions
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in your values
uvicorn main:app --reload
```

API docs available at <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local      # fill in your values
npm run dev
```

App available at <http://localhost:5173>.

## Environment Variables

| File | Purpose |
|---|---|
| `backend/.env.example` | Backend secrets (DB, API keys, JWT) |
| `frontend/.env.example` | Frontend config (API/WS URLs) |

Copy each file to `.env` / `.env.local` and fill in real values. **Never commit secret files.**

## Running Tests

```bash
cd backend
pytest
```

## License

MIT
