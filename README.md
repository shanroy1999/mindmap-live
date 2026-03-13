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
| Backend | Python, FastAPI, SQLAlchemy |
| Frontend | React, TypeScript, Vite |
| Database | PostgreSQL |
| Cache / Pub-Sub | Redis |
| AI | Anthropic Claude API |
| Auth | JWT |

## Project Structure
```
mindmap-live/
├── backend/          # FastAPI application
│   ├── routers/      # API route handlers
│   ├── models/       # SQLAlchemy ORM models
│   ├── schemas/      # Pydantic request/response schemas
│   ├── services/     # Business logic
│   ├── db/           # Database connection and session
│   └── tests/        # pytest test suite
├── frontend/         # React + TypeScript application
└── docs/             # Architecture and design documents
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
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your values
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

See `backend/.env.example` for the full list of required variables.

## License

MIT
