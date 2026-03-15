# Architecture

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Graph Data Model](#2-graph-data-model)
3. [REST API Design](#3-rest-api-design)
4. [Why Adjacency List over a Graph Database](#4-why-adjacency-list-over-a-graph-database)
5. [WebSocket Architecture](#5-websocket-architecture)
6. [Key Design Decisions](#6-key-design-decisions)

---

## 1. System Overview

MindMap Live follows a layered client-server architecture with a dedicated real-time sync layer.

```
┌──────────────────────────────────────────────────────────────┐
│                    Browser (React + TypeScript)               │
│                                                              │
│   ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│   │  Canvas UI  │   │  REST client │   │   WS client     │  │
│   │  (nodes,    │   │  (api/)      │   │  (hooks/        │  │
│   │   edges)    │   │              │   │   useWebSocket) │  │
│   └─────────────┘   └──────┬───────┘   └────────┬────────┘  │
└──────────────────────────  │ ─────────────────── │ ──────────┘
                             │ HTTP/REST            │ WebSocket
                             │                      │
┌────────────────────────────▼──────────────────────▼──────────┐
│                      FastAPI Backend                          │
│                                                              │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │   Routers    │  │    Services    │  │   WS Manager     │  │
│  │  (HTTP layer)│  │ (business      │  │  (connection     │  │
│  │              │  │  logic)        │  │   registry +     │  │
│  │  /api/nodes  │  │                │  │   broadcast)     │  │
│  │  /api/edges  │  │  node_service  │  │                  │  │
│  │  /api/users  │  │  edge_service  │  │  subscribes to   │  │
│  │  /api/maps   │  │  ai_service    │  │  Redis channel   │  │
│  │  /api/auth   │  │  user_service  │  │                  │  │
│  └──────┬───────┘  └───────┬────────┘  └────────┬─────────┘  │
└─────────│──────────────────│───────────────────  │ ───────────┘
          │ SQLAlchemy        │                     │ pub/sub
          │                  │                     │
┌─────────▼──────────────────▼──┐   ┌──────────────▼──────────┐
│          PostgreSQL            │   │          Redis           │
│                               │   │                         │
│  nodes  edges  users  maps    │   │  PUBLISH/SUBSCRIBE      │
│  map_members                  │   │  channel per map_id      │
└───────────────────────────────┘   └─────────────────────────┘
```

---

## 2. Graph Data Model

### Design Approach

MindMap Live represents knowledge graphs using the **adjacency list** pattern directly in PostgreSQL. Each node is a row in `nodes`; each directed edge is a row in `edges` that references two node IDs. This is the simplest correct representation for sparse graphs where the primary access patterns are: fetch all nodes for a map, fetch all edges for a map, and look up neighbours of a node.

### Full Schema

#### Table: `users`

Stores authenticated user accounts.

```sql
CREATE TABLE users (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT        NOT NULL UNIQUE,
    display_name     TEXT        NOT NULL,
    hashed_password  TEXT        NOT NULL,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Application never generates this; delegated to Postgres |
| `email` | `TEXT` | NOT NULL, UNIQUE | Normalised to lowercase before insert |
| `display_name` | `TEXT` | NOT NULL | Display-only; not used for auth |
| `hashed_password` | `TEXT` | NOT NULL | bcrypt hash; plain-text password never persisted |
| `is_active` | `BOOLEAN` | NOT NULL, default `TRUE` | Soft-disable without deletion |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `NOW()` | Always stored in UTC |

---

#### Table: `maps`

A map is a named workspace that contains a graph. Users can own or be members of multiple maps.

```sql
CREATE TABLE maps (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    description TEXT,
    is_public   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_maps_owner ON maps (owner_id);
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `owner_id` | `UUID` | FK → `users.id` CASCADE | The user who created the map |
| `title` | `TEXT` | NOT NULL | |
| `description` | `TEXT` | nullable | Optional long-form description |
| `is_public` | `BOOLEAN` | NOT NULL, default `FALSE` | Public maps are viewable without auth |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | Updated by trigger on every mutation |

---

#### Table: `map_members`

Join table for access control. The owner is also inserted here as `role = 'owner'` on map creation, so a single query on `map_members` determines all access.

```sql
CREATE TYPE map_role AS ENUM ('owner', 'editor', 'viewer');

CREATE TABLE map_members (
    map_id     UUID     NOT NULL REFERENCES maps  (id) ON DELETE CASCADE,
    user_id    UUID     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role       map_role NOT NULL DEFAULT 'viewer',
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (map_id, user_id)
);

CREATE INDEX idx_map_members_user ON map_members (user_id);
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `map_id` | `UUID` | PK part, FK → `maps.id` CASCADE | |
| `user_id` | `UUID` | PK part, FK → `users.id` CASCADE | |
| `role` | `map_role` | NOT NULL, default `'viewer'` | Controls read/write permission checks |
| `joined_at` | `TIMESTAMPTZ` | NOT NULL | |

---

#### Table: `nodes`

The core entity. A node represents a concept, idea, or piece of knowledge on the canvas.

```sql
CREATE TABLE nodes (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    map_id      UUID        NOT NULL REFERENCES maps (id) ON DELETE CASCADE,
    label       TEXT        NOT NULL,
    description TEXT,
    color       TEXT        NOT NULL DEFAULT '#6366f1',
    x           DOUBLE PRECISION NOT NULL DEFAULT 0,
    y           DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_by  UUID        REFERENCES users (id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_nodes_map     ON nodes (map_id);
CREATE INDEX idx_nodes_created ON nodes (map_id, created_at DESC);
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `map_id` | `UUID` | NOT NULL, FK → `maps.id` CASCADE | All nodes belong to exactly one map |
| `label` | `TEXT` | NOT NULL | Short display text on the canvas |
| `description` | `TEXT` | nullable | Markdown-formatted long-form content |
| `color` | `TEXT` | NOT NULL, default `'#6366f1'` | Hex colour for canvas rendering |
| `x` | `DOUBLE PRECISION` | NOT NULL, default `0` | Canvas x-coordinate in logical pixels |
| `y` | `DOUBLE PRECISION` | NOT NULL, default `0` | Canvas y-coordinate in logical pixels |
| `created_by` | `UUID` | nullable, FK → `users.id` SET NULL | Preserved for audit even if user is deleted |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | Updated by trigger on position or label change |

**Index rationale:**
- `idx_nodes_map` — the most common query is `WHERE map_id = $1`; this index makes it O(log n).
- `idx_nodes_created` — supports paginated timeline views, ordered newest-first within a map.

---

#### Table: `edges`

A directed relationship from a source node to a target node within the same map.

```sql
CREATE TABLE edges (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    map_id      UUID        NOT NULL REFERENCES maps  (id) ON DELETE CASCADE,
    source_id   UUID        NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    target_id   UUID        NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    label       TEXT,
    created_by  UUID        REFERENCES users (id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT no_self_loops CHECK (source_id <> target_id),
    CONSTRAINT unique_directed_edge UNIQUE (map_id, source_id, target_id)
);

CREATE INDEX idx_edges_map        ON edges (map_id);
CREATE INDEX idx_edges_source     ON edges (source_id);
CREATE INDEX idx_edges_target     ON edges (target_id);
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `map_id` | `UUID` | NOT NULL, FK → `maps.id` CASCADE | Denormalised from source/target for fast map-scoped queries |
| `source_id` | `UUID` | NOT NULL, FK → `nodes.id` CASCADE | Origin of the directed relationship |
| `target_id` | `UUID` | NOT NULL, FK → `nodes.id` CASCADE | Destination of the directed relationship |
| `label` | `TEXT` | nullable | Relationship label rendered on the edge |
| `created_by` | `UUID` | nullable, FK → `users.id` SET NULL | |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | |

**Constraints:**
- `no_self_loops` — prevents `source_id = target_id` at the database level.
- `unique_directed_edge` — prevents duplicate directed edges between the same two nodes in the same map. Undirected duplicates (A→B and B→A) are allowed by design.

**Index rationale:**
- `idx_edges_map` — primary access pattern: fetch all edges for a map.
- `idx_edges_source` / `idx_edges_target` — support neighbour-lookup queries: "find all edges where this node is the source/target."

---

#### `updated_at` Trigger (applied to `nodes` and `maps`)

Rather than relying on application code to set `updated_at`, a trigger handles it automatically.

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nodes_updated_at
    BEFORE UPDATE ON nodes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_maps_updated_at
    BEFORE UPDATE ON maps
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### Entity Relationship Summary

```
users ──< map_members >── maps ──< nodes
                           │
                           └──────< edges (source_id, target_id → nodes)
```

- A `user` can be a member of many `maps`; a `map` has many `members`.
- A `map` owns many `nodes`; deleting a map cascades to all its nodes and edges.
- An `edge` references two `nodes` (both must exist in the same map).

---

## 3. REST API Design

All endpoints are prefixed with `/api`. Authenticated endpoints require a `Bearer <JWT>` header.

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | None | Create a new user account |
| `POST` | `/api/auth/login` | None | Exchange credentials for a JWT access token |
| `POST` | `/api/auth/refresh` | Refresh token | Issue a new access token |

**`POST /api/auth/register`**
```
Request:  { "email": string, "display_name": string, "password": string }
Response: 201 { "id": uuid, "email": string, "display_name": string, "created_at": timestamp }
Errors:   409 if email already registered
          422 if request body is malformed
```

**`POST /api/auth/login`**
```
Request:  { "email": string, "password": string }
Response: 200 { "access_token": string, "token_type": "bearer", "expires_in": number }
Errors:   401 if credentials are invalid
```

---

### Maps

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/maps` | Required | List maps the caller is a member of |
| `POST` | `/api/maps` | Required | Create a new map |
| `GET` | `/api/maps/{map_id}` | Required* | Get map metadata |
| `PATCH` | `/api/maps/{map_id}` | Owner/Editor | Update map title or description |
| `DELETE` | `/api/maps/{map_id}` | Owner | Delete a map and all its contents |
| `GET` | `/api/maps/{map_id}/members` | Required* | List members and their roles |
| `POST` | `/api/maps/{map_id}/members` | Owner | Invite a user to a map |
| `PATCH` | `/api/maps/{map_id}/members/{user_id}` | Owner | Change a member's role |
| `DELETE` | `/api/maps/{map_id}/members/{user_id}` | Owner | Remove a member |

> \* Public maps (`is_public = true`) are accessible without authentication.

**`GET /api/maps`**
```
Response: 200 [{ "id", "title", "description", "is_public", "role", "created_at", "updated_at" }, ...]
```

**`POST /api/maps`**
```
Request:  { "title": string, "description"?: string, "is_public"?: boolean }
Response: 201 { map object }
```

**`DELETE /api/maps/{map_id}`**
```
Response: 204 No Content
Errors:   403 if caller is not the owner
          404 if map does not exist
```

---

### Nodes

All node endpoints are scoped to a map. Callers must have at least `viewer` role to read and at least `editor` role to write.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/maps/{map_id}/nodes` | Required* | List all nodes in a map |
| `POST` | `/api/maps/{map_id}/nodes` | Editor | Create a node |
| `GET` | `/api/maps/{map_id}/nodes/{node_id}` | Required* | Get a single node |
| `PATCH` | `/api/maps/{map_id}/nodes/{node_id}` | Editor | Update label, description, position, or colour |
| `DELETE` | `/api/maps/{map_id}/nodes/{node_id}` | Editor | Delete a node (also deletes its edges) |

**`POST /api/maps/{map_id}/nodes`**
```
Request:  { "label": string, "description"?: string, "color"?: string, "x"?: number, "y"?: number }
Response: 201 { "id", "map_id", "label", "description", "color", "x", "y", "created_by", "created_at", "updated_at" }
Errors:   403 caller lacks editor role
          404 map not found
```

**`PATCH /api/maps/{map_id}/nodes/{node_id}`**
```
Request:  any subset of { "label", "description", "color", "x", "y" }
Response: 200 { updated node object }
Errors:   403, 404
```

**`DELETE /api/maps/{map_id}/nodes/{node_id}`**
```
Response: 204 No Content
Errors:   403, 404
Side effects: all edges where source_id or target_id = node_id are deleted (CASCADE)
```

---

### Edges

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/maps/{map_id}/edges` | Required* | List all edges in a map |
| `POST` | `/api/maps/{map_id}/edges` | Editor | Create an edge |
| `GET` | `/api/maps/{map_id}/edges/{edge_id}` | Required* | Get a single edge |
| `PATCH` | `/api/maps/{map_id}/edges/{edge_id}` | Editor | Update the edge label |
| `DELETE` | `/api/maps/{map_id}/edges/{edge_id}` | Editor | Delete an edge |

**`POST /api/maps/{map_id}/edges`**
```
Request:  { "source_id": uuid, "target_id": uuid, "label"?: string }
Response: 201 { "id", "map_id", "source_id", "target_id", "label", "created_by", "created_at" }
Errors:   400 if source_id == target_id
          404 if source or target node does not exist in this map
          409 if this directed edge already exists
```

---

### AI

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/maps/{map_id}/ai/suggest-edges` | Editor | Ask Claude to suggest new relationships |
| `POST` | `/api/maps/{map_id}/ai/summarise` | Viewer | Ask Claude to summarise the graph |

**`POST /api/maps/{map_id}/ai/suggest-edges`**
```
Request:  { "node_ids"?: uuid[] }   // omit to use all nodes in the map
Response: 200 {
  "suggestions": [
    { "source_label": string, "target_label": string, "reason": string },
    ...
  ]
}
```

> Suggestions are returned as labels, not IDs, so the client can present them before the user decides to create the edges. No edges are written by this endpoint.

---

### Error Response Shape

All error responses use a consistent envelope:

```json
{
  "detail": "Human-readable error message"
}
```

FastAPI's default 422 validation errors follow the standard Pydantic format:
```json
{
  "detail": [
    { "loc": ["body", "field_name"], "msg": "field required", "type": "value_error.missing" }
  ]
}
```

---

## 4. Why Adjacency List over a Graph Database

### The Question

Given that MindMap Live is literally a graph application, it is reasonable to ask: why not use **Neo4j**, **Amazon Neptune**, or **ArangoDB** instead of encoding graph structure in PostgreSQL?

### Where Graph Databases Win

Dedicated graph databases excel at:

1. **Multi-hop traversals** — queries like "find all nodes reachable from node A within 5 hops" or "shortest path between A and B" execute in near-constant time because the storage engine walks pointer chains rather than performing join operations.
2. **Highly connected data** — social networks, fraud graphs, and recommendation engines routinely have millions of edges per node. Graph databases store and traverse these efficiently.
3. **Schema-free relationships** — Cypher or Gremlin make it natural to attach arbitrary properties to relationships without schema migrations.

### Why They Are Overkill Here

MindMap Live's graphs are structurally small and access patterns are simple:

| Access pattern | SQL query complexity |
|---|---|
| Load all nodes for a map | `SELECT * FROM nodes WHERE map_id = $1` — single index scan |
| Load all edges for a map | `SELECT * FROM edges WHERE map_id = $1` — single index scan |
| Get neighbours of a node | `SELECT * FROM edges WHERE source_id = $1 OR target_id = $1` — two index scans merged |
| Check if an edge exists | `SELECT 1 FROM edges WHERE map_id=$1 AND source_id=$2 AND target_id=$3` — unique index lookup |

None of these queries involve multi-hop traversal. The entire graph for a map is loaded into the client canvas in one or two queries; graph traversal happens **in the browser**, not in the database.

Typical MindMap Live graph sizes:

- Nodes per map: **10 – 500** (P99)
- Edges per map: **5 – 1 000** (P99)

At this scale, even a full table scan would be sub-millisecond. The `idx_nodes_map` and `idx_edges_map` indexes make these queries trivially fast.

### Operational and Ecosystem Advantages of PostgreSQL

Beyond raw query performance:

- **Single data store.** Users, authentication, access control (map_members), and graph data all live in Postgres. One backup strategy, one monitoring surface, one operational runbook.
- **ACID transactions.** Creating a node and broadcasting the WebSocket event can be wrapped in a transaction. Rollback on failure leaves no partial state.
- **Foreign key integrity.** `CASCADE` on node deletion guarantees orphaned edges can never exist. A graph database would require this to be enforced in application code.
- **Rich ecosystem.** SQLAlchemy, Alembic, pgAdmin, pg_dump, read replicas, connection pooling via PgBouncer — all mature and well-understood.
- **Hosting.** Managed PostgreSQL is available on every major cloud provider (RDS, Cloud SQL, Supabase, Neon). Managed Neo4j Aura exists but is more expensive and less universally supported.
- **Team familiarity.** Most backend engineers know SQL. Cypher/Gremlin is a specialised skill that increases onboarding friction.

### When We Would Reconsider

If MindMap Live evolves to require:

- **AI-powered path-finding** (e.g., "find the knowledge chain connecting Concept A to Concept B")
- **Graph-ML features** that require running algorithms like PageRank, community detection, or betweenness centrality at scale
- Maps routinely containing **10 000+ nodes**

…then migrating the graph layer to a dedicated store (or using the `pg_routing` extension / Apache AGE for in-Postgres graph queries) would be worth evaluating. The PostgreSQL schema is intentionally simple enough that this migration would not require rewriting application business logic — only the data access layer.

### Decision Summary

| Criterion | PostgreSQL + Adjacency List | Neo4j |
|---|---|---|
| Multi-hop traversal performance | Adequate for <1 000 nodes | Excellent |
| Simple fetch-all queries | Excellent | Good |
| Transactional integrity | Excellent (ACID) | Good (ACID in Enterprise) |
| Operational complexity | Low (one service) | Higher (separate service) |
| Hosting cost | Low | Higher |
| Team familiarity | High | Low |
| Graph-specific query language | Not needed | Cypher (powerful but specialised) |

**Verdict:** PostgreSQL is the right choice for v1. Revisit if graph traversal or scale requirements change.

---

## 5. WebSocket Architecture

### Goals

1. Every mutation (node created, node moved, edge created, edge deleted) is broadcast to all other browser tabs connected to the same map within **< 200 ms**.
2. The architecture scales horizontally — multiple backend processes can run behind a load balancer without clients missing events.
3. The client can reconnect transparently after a network interruption.

### Connection Lifecycle

```
Client                         FastAPI Process                   Redis
  │                                  │                             │
  │  GET /ws/maps/{map_id}           │                             │
  │  (Upgrade: websocket)            │                             │
  ├─────────────────────────────────►│                             │
  │                                  │  SUBSCRIBE map:{map_id}     │
  │                                  ├────────────────────────────►│
  │  ← 101 Switching Protocols       │                             │
  │◄─────────────────────────────────┤                             │
  │                                  │                             │
  │  [connection is now open]        │                             │
  │                                  │                             │
```

On connection, the backend:
1. Validates the JWT from the `?token=` query parameter (WebSocket handshakes cannot carry custom headers).
2. Confirms the user has at least `viewer` access to the map.
3. Registers the connection in an in-process `ConnectionManager` keyed by `map_id`.
4. Subscribes (or re-uses an existing subscription) to the Redis channel `map:{map_id}`.

### Mutation Flow (Write Path)

```
Browser A               FastAPI (any process)          Redis          FastAPI (any process)       Browser B
    │                          │                         │                    │                       │
    │  PATCH /api/maps/        │                         │                    │                       │
    │    {map_id}/nodes/{id}   │                         │                    │                       │
    ├─────────────────────────►│                         │                    │                       │
    │                          │  BEGIN transaction      │                    │                       │
    │                          │  UPDATE nodes ...       │                    │                       │
    │                          │  COMMIT                 │                    │                       │
    │                          │                         │                    │                       │
    │                          │  PUBLISH map:{map_id}   │                    │                       │
    │                          │  { type: "node:updated",│                    │                       │
    │                          │    payload: {...} }      │                    │                       │
    │                          ├────────────────────────►│                    │                       │
    │                          │                         │  MESSAGE delivered │                       │
    │  ← 200 { updated node }  │                         ├───────────────────►│                       │
    │◄─────────────────────────┤                         │                    │                       │
    │                          │                         │                    │  broadcast to all WS  │
    │                          │                         │                    │  connections for       │
    │                          │                         │                    │  this map_id           │
    │                          │                         │                    ├──────────────────────►│
    │                          │                         │                    │                       │
    │                          │                         │                    │  { type: "node:updated"│
    │                          │                         │                    │    payload: {...} }    │
    │  (Browser A's own WS     │                         │                    │◄──────────────────────┤
    │   connection also        │                         │                    │                       │
    │   receives the event,    │                         │                    │                       │
    │   which it ignores if    │                         │                    │                       │
    │   it originated it)      │                         │                    │                       │
```

**Key detail:** The REST response to Browser A is sent immediately after the database commit. The PUBLISH to Redis is a fire-and-forget call made synchronously before the response returns. This means the 200 response and the WS broadcast are causally ordered: other clients never see an event before the write is durable.

### Event Envelope

All WebSocket messages follow a typed envelope:

```json
{
  "type": "node:updated",
  "map_id": "f47ac10b-...",
  "actor_id": "550e8400-...",
  "payload": {
    "id": "6ba7b810-...",
    "label": "Revised label",
    "x": 320.5,
    "y": 180.0,
    "updated_at": "2026-03-13T10:22:01Z"
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `type` | `string` | One of the event types listed below |
| `map_id` | `UUID` | Allows a client subscribed to multiple maps to route the event |
| `actor_id` | `UUID` | The user who triggered the mutation; clients use this to suppress echoing their own changes |
| `payload` | `object` | The full updated object (not a diff), so clients can replace local state directly |

### Event Types

| Type | Triggered by | Payload |
|---|---|---|
| `node:created` | `POST /api/maps/{id}/nodes` | Full `NodeRead` object |
| `node:updated` | `PATCH /api/maps/{id}/nodes/{id}` | Full `NodeRead` object |
| `node:deleted` | `DELETE /api/maps/{id}/nodes/{id}` | `{ "id": uuid }` |
| `edge:created` | `POST /api/maps/{id}/edges` | Full `EdgeRead` object |
| `edge:deleted` | `DELETE /api/maps/{id}/edges/{id}` | `{ "id": uuid }` |
| `member:joined` | `POST /api/maps/{id}/members` | `{ "user_id", "display_name", "role" }` |

### ConnectionManager (in-process)

```python
class ConnectionManager:
    """
    Maintains the set of active WebSocket connections grouped by map_id.
    One instance per process; Redis bridges across processes.
    """
    _connections: dict[str, set[WebSocket]]  # map_id → set of sockets

    async def connect(map_id: str, ws: WebSocket) -> None: ...
    async def disconnect(map_id: str, ws: WebSocket) -> None: ...
    async def broadcast(map_id: str, message: dict) -> None: ...
        # iterates self._connections[map_id], sends to each,
        # silently removes any socket that raises on send
```

### Client Reconnection

The frontend `useWebSocket` hook implements exponential backoff reconnection:

```
disconnect → wait 1s → reconnect
disconnect → wait 2s → reconnect
disconnect → wait 4s → reconnect
... (capped at 30s)
```

On reconnect, the client immediately calls `GET /api/maps/{id}/nodes` and `GET /api/maps/{id}/edges` to reconcile any events missed during the disconnection window. This "fetch on reconnect" pattern is simpler and more reliable than trying to replay missed events from a durable event log.

### Horizontal Scaling

```
                   Load Balancer
                  (sticky sessions)
                 /                \
     FastAPI Process 1        FastAPI Process 2
     ConnectionManager         ConnectionManager
     Browser A (WS)            Browser B (WS)
     Browser C (WS)
           │                         │
           └──────────────┬──────────┘
                      Redis
                  map:abc channel
```

Redis pub/sub decouples the broadcast from the process that received the write. When Process 1 commits a write and publishes to Redis, Process 2's subscriber callback fires and broadcasts to Browser B — even though Process 2 never handled the HTTP request.

Sticky sessions (affinity by `map_id` or session cookie) are optional but reduce redundant Redis subscriptions. The system is correct without them.

---

## 6. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Monorepo | Single git repository | Atomic cross-layer commits; simpler CI |
| Primary keys | `UUID` generated by Postgres (`gen_random_uuid()`) | No application-layer ID generation; works across replicas |
| Graph storage | PostgreSQL adjacency list | See Section 4 |
| Real-time | WebSocket + Redis pub/sub | Scales horizontally; no polling; low latency |
| Auth | JWT (stateless access token + refresh token) | No session table; scales with multiple processes |
| Password hashing | bcrypt via passlib | Industry standard; configurable work factor |
| WS auth | JWT in `?token=` query param | WebSocket upgrades cannot carry Authorization header |
| Optimistic UI | Client applies changes before WS confirmation | Eliminates perceived latency on fast connections |
| `updated_at` | Database trigger | Prevents application bugs from leaving stale timestamps |
| No hardcoded secrets | Environment variables only | Follows 12-factor app principles |

---

## 7. Database Migrations

### Why Alembic instead of `create_all()`

SQLAlchemy's `Base.metadata.create_all()` is convenient for prototyping, but
it is **not suitable for production** because it can only create tables that do
not exist yet — it cannot alter, rename, or drop columns, change constraints,
or update indexes in an already-running database.  Every production deployment
that changes the schema requires a coordinated migration step.

Alembic provides:

| Feature | `create_all()` | Alembic |
|---|---|---|
| Create tables from scratch | ✅ | ✅ |
| Add / remove columns | ❌ | ✅ |
| Rename columns or tables | ❌ | ✅ |
| Change column types | ❌ | ✅ |
| Manage indexes and constraints | ❌ | ✅ |
| Rollback a bad deployment | ❌ | ✅ (`downgrade`) |
| Version-controlled history | ❌ | ✅ (`versions/`) |
| Preview SQL before applying | ❌ | ✅ (`--sql`) |
| CI/CD integration | ❌ | ✅ |

### Project layout

```
backend/
├── alembic.ini                   # Alembic config (script_location, logging)
└── alembic/
    ├── env.py                    # Runtime config: DB URL, target_metadata
    ├── script.py.mako            # Template for generated migration files
    └── versions/
        └── 20240315_a1b2c3d4e5f6_create_initial_schema.py
```

### Configuration

`alembic.ini` intentionally leaves `sqlalchemy.url` blank.  `alembic/env.py`
reads `DATABASE_URL` from the environment (or `backend/.env`) at runtime and
normalises it to `postgresql+asyncpg://` so the same connection string works
for both the FastAPI app and Alembic.

Alembic runs migrations **synchronously** inside `connection.run_sync()` even
though the application uses asyncpg — this lets Alembic use its standard
synchronous DDL API while the transport layer remains async.

### Common commands

```bash
# Apply all pending migrations (run from backend/).
alembic upgrade head

# Roll back the most recent migration.
alembic downgrade -1

# Show the current revision applied to the database.
alembic current

# Show all revisions and which one is current.
alembic history --verbose

# Generate a new migration from ORM model changes.
alembic revision --autogenerate -m "add node_type column"

# Preview the SQL that upgrade head would run (no DB connection needed).
alembic upgrade head --sql > upgrade.sql
```

### Writing migrations

Alembic can autogenerate a migration skeleton from the diff between the live
database schema and `Base.metadata`, but **always review the generated file**
before committing:

- Autogenerate does not detect server defaults, triggers, or custom SQL.
- Add raw SQL with `op.execute()` for triggers, functions, or extensions.
- Drop tables/indexes in reverse dependency order in `downgrade()`.
- Create the `map_role` ENUM type before any table that references it; drop
  it after all tables that reference it are dropped.

### First migration

`20240315_a1b2c3d4e5f6_create_initial_schema.py` creates:

- `map_role` ENUM type (`owner`, `editor`, `viewer`)
- `users` — email unique index
- `maps` — `owner_id` index
- `map_members` — composite PK (`map_id`, `user_id`), `user_id` index
- `nodes` — `(map_id)` and `(map_id, created_at)` indexes
- `edges` — `no_self_loops` CHECK, `unique_directed_edge` UNIQUE, three indexes
- `set_updated_at()` PL/pgSQL function + triggers on `maps` and `nodes`
