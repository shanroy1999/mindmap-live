"""WebSocket connection manager with local delivery and Redis pub/sub relay.

Architecture
────────────
``broadcast`` delivers messages in two steps:

1. **Local delivery** — iterate the in-process room list and send directly to
   every WebSocket in this worker (excluding the sender).  This works even when
   Redis is unavailable (dev environments, Redis restarts, etc.).

2. **Redis relay** — publish to ``mindmap:{map_id}`` so that workers running in
   other processes/containers also receive the message and forward it to their
   local connections.  The envelope carries ``_wid`` (worker ID) so that the
   subscribe loop in the *same* worker can skip messages it already delivered
   directly, preventing double delivery.

This design is correct for both single-server (Redis optional) and horizontally
scaled (multi-worker behind a load balancer) deployments.
"""

import asyncio
import json
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# Unique ID for this worker process — embedded in Redis envelopes so the
# subscribe loop can skip messages that were already delivered locally.
_WORKER_ID: str = str(uuid.uuid4())

import redis.asyncio as aioredis
from fastapi import WebSocket

# ── Presence colour palette ───────────────────────────────────────────────────
# Six visually distinct colours used to identify collaborators.
_PRESENCE_COLORS: list[str] = [
    '#f472b6',  # pink
    '#34d399',  # emerald
    '#60a5fa',  # sky-blue
    '#fb923c',  # orange
    '#a78bfa',  # violet
    '#facc15',  # yellow
]


def user_presence_color(user_id: uuid.UUID) -> str:
    """Return a deterministic colour from the presence palette for *user_id*."""
    return _PRESENCE_COLORS[user_id.int % len(_PRESENCE_COLORS)]


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@dataclass
class _Connection:
    websocket: WebSocket
    user_id: uuid.UUID
    display_name: str
    color: str
    # Unique ID for this connection — used to exclude the sender in the
    # subscribe loop without exposing WebSocket object identity across the
    # Redis boundary.
    cid: str = field(default_factory=lambda: str(uuid.uuid4()))


class ConnectionManager:
    """Manages local WebSocket connections and coordinates via Redis pub/sub.

    One global instance is created at module level and shared across all
    WebSocket route handlers::

        @app.websocket("/ws/mindmaps/{mindmap_id}")
        async def ws_endpoint(websocket, mindmap_id, user=Depends(...)):
            await manager.connect(websocket, mindmap_id, user.id)
            try:
                while True:
                    data = await websocket.receive_json()
                    await manager.broadcast(data, mindmap_id, exclude_websocket=websocket)
            except WebSocketDisconnect:
                pass
            finally:
                await manager.disconnect(websocket, mindmap_id)
    """

    def __init__(self) -> None:
        self._rooms: dict[str, list[_Connection]] = defaultdict(list)
        # One subscribe task per map room keeps the Redis listener alive for
        # as long as at least one client is connected to that room.
        self._subscriber_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]
        # Shared publish client — lazily initialised on first broadcast.
        self._pub: Optional[aioredis.Redis] = None  # type: ignore[type-arg]

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _publisher(self) -> aioredis.Redis:  # type: ignore[type-arg]
        """Return (and lazily create) the shared publish-only Redis client.

        The client is created on the first ``broadcast`` call — never at import
        time or during startup — so that routes which don't use WebSockets are
        completely unaffected by Redis availability.
        """
        if self._pub is None:
            self._pub = aioredis.from_url(
                _redis_url(),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._pub

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        mindmap_id: uuid.UUID,
        user_id: uuid.UUID,
        display_name: str,
    ) -> str:
        """Accept *websocket*, register it in the room, and announce the arrival.

        Broadcasts a ``user_joined`` event to every peer already in the room
        (excluding the new connection itself).  Task lifecycle is the
        responsibility of the caller (the WebSocket route handler).

        Args:
            websocket:    The incoming WebSocket connection to accept and track.
            mindmap_id:   The map room this client is joining.
            user_id:      The authenticated user.
            display_name: Human-readable name shown to other collaborators.

        Returns:
            The new connection's ``cid`` (used by the caller to build the
            initial ``room_state`` snapshot without including the joiner).
        """
        await websocket.accept()
        key = str(mindmap_id)
        color = user_presence_color(user_id)
        conn = _Connection(
            websocket=websocket,
            user_id=user_id,
            display_name=display_name,
            color=color,
        )
        self._rooms[key].append(conn)

        try:
            await self.broadcast(
                {
                    "type": "user_joined",
                    "userId": str(user_id),
                    "displayName": display_name,
                    "color": color,
                },
                mindmap_id,
                exclude_websocket=websocket,
            )
        except Exception:
            pass  # Don't fail the connection if Redis is unreachable.

        return conn.cid

    async def disconnect(
        self,
        websocket: WebSocket,
        mindmap_id: uuid.UUID,
    ) -> None:
        """Remove *websocket* from the room and broadcast a ``user_left`` event.

        Cleans up the room dict when the last client leaves.  Task cancellation
        is the responsibility of the caller (the WebSocket route handler).

        Args:
            websocket:  The WebSocket that disconnected.
            mindmap_id: The map room the client was connected to.
        """
        key = str(mindmap_id)

        # Capture user info before removing so we can broadcast the departure.
        leaving: Optional[_Connection] = next(
            (c for c in self._rooms.get(key, []) if c.websocket is websocket),
            None,
        )

        self._rooms[key] = [c for c in self._rooms[key] if c.websocket is not websocket]
        if not self._rooms[key]:
            del self._rooms[key]

        if leaving is not None:
            try:
                await self.broadcast(
                    {
                        "type": "user_left",
                        "userId": str(leaving.user_id),
                        "displayName": leaving.display_name,
                    },
                    mindmap_id,
                )
            except Exception:
                pass  # Best-effort; room may be empty or Redis may be unreachable.

    # ── Subscriber-task accessors (used by the route handler) ─────────────────

    def get_subscriber_task(self, mindmap_id: uuid.UUID) -> Optional[asyncio.Task]:  # type: ignore[type-arg]
        """Return the running subscribe task for *mindmap_id*, or None."""
        return self._subscriber_tasks.get(str(mindmap_id))

    def set_subscriber_task(
        self,
        mindmap_id: uuid.UUID,
        task: asyncio.Task,  # type: ignore[type-arg]
    ) -> None:
        """Store *task* as the subscribe task for *mindmap_id*."""
        self._subscriber_tasks[str(mindmap_id)] = task

    def pop_subscriber_task(
        self,
        mindmap_id: uuid.UUID,
    ) -> Optional[asyncio.Task]:  # type: ignore[type-arg]
        """Remove and return the subscribe task for *mindmap_id*, or None."""
        return self._subscriber_tasks.pop(str(mindmap_id), None)

    def room_is_empty(self, mindmap_id: uuid.UUID) -> bool:
        """Return True if no connections remain in *mindmap_id*'s room."""
        return str(mindmap_id) not in self._rooms

    def get_room_users(
        self,
        mindmap_id: uuid.UUID,
        exclude_cid: Optional[str] = None,
    ) -> list[dict]:
        """Return user-info dicts for all connections in *mindmap_id*'s room.

        Args:
            mindmap_id:  The target map room.
            exclude_cid: Skip the connection with this cid — used to exclude
                         the newly joined user from the ``room_state`` snapshot
                         sent back to them on connect.

        Returns:
            A list of ``{"userId", "displayName", "color"}`` dicts.
        """
        key = str(mindmap_id)
        return [
            {
                "userId": str(conn.user_id),
                "displayName": conn.display_name,
                "color": conn.color,
            }
            for conn in self._rooms.get(key, [])
            if conn.cid != exclude_cid
        ]

    async def broadcast(
        self,
        message: dict,
        mindmap_id: uuid.UUID,
        exclude_websocket: Optional[WebSocket] = None,
    ) -> None:
        """Deliver *message* locally then relay via Redis for other workers.

        Step 1 — direct local delivery to every WebSocket in this process
        (excluding the sender).  This works without Redis and is the primary
        delivery path for single-server deployments.

        Step 2 — publish to Redis so other workers forward the message to
        their local connections.  The envelope carries ``_wid`` so this
        worker's subscribe loop knows to skip these messages (already done).

        Args:
            message:           JSON-serialisable dict to broadcast.
            mindmap_id:        Target map room.
            exclude_websocket: The sending connection; its *cid* is used to
                               identify the sender so they are excluded.
        """
        key = str(mindmap_id)

        sender_cid: Optional[str] = None
        if exclude_websocket is not None:
            for conn in self._rooms.get(key, []):
                if conn.websocket is exclude_websocket:
                    sender_cid = conn.cid
                    break

        # ── Step 1: deliver directly to all local connections ─────────────
        dead: list[_Connection] = []
        for conn in list(self._rooms.get(key, [])):
            if conn.cid == sender_cid:
                continue
            try:
                await conn.websocket.send_json(message)
            except Exception:
                dead.append(conn)

        for conn in dead:
            self._rooms[key] = [c for c in self._rooms[key] if c is not conn]

        # ── Step 2: relay to other workers via Redis (best-effort) ────────
        try:
            envelope = json.dumps({"_cid": sender_cid, "_wid": _WORKER_ID, "data": message})
            pub = await self._publisher()
            await pub.publish(f"mindmap:{key}", envelope)
        except Exception:
            pass  # Redis unavailable — local delivery already completed above.

    async def subscribe(self, mindmap_id: uuid.UUID) -> None:
        """Listen on ``mindmap:{mindmap_id}`` and forward messages to local sockets.

        Runs until cancelled (which happens automatically when the last client
        in the room disconnects).  Uses a dedicated Redis connection so the
        blocking listen loop never contends with the publish client.

        Args:
            mindmap_id: The map room whose Redis channel to subscribe to.
        """
        key = str(mindmap_id)
        channel = f"mindmap:{key}"

        redis_sub = aioredis.from_url(
            _redis_url(),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        pubsub = redis_sub.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue

                try:
                    envelope = json.loads(raw["data"])
                    sender_cid: Optional[str] = envelope.get("_cid")
                    sender_wid: Optional[str] = envelope.get("_wid")
                    data: dict = envelope["data"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

                # Skip messages published by this worker — already delivered
                # directly in broadcast() to avoid double delivery.
                if sender_wid == _WORKER_ID:
                    continue

                dead: list[_Connection] = []
                for conn in list(self._rooms.get(key, [])):
                    if conn.cid == sender_cid:
                        continue
                    try:
                        await conn.websocket.send_json(data)
                    except Exception:
                        dead.append(conn)

                for conn in dead:
                    self._rooms[key] = [c for c in self._rooms[key] if c is not conn]

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await redis_sub.aclose()


# Singleton shared by all WebSocket route handlers.
# Instantiated here (not at import time inside lifespan) but the constructor
# does NOT connect to Redis — all Redis I/O is deferred until the first
# WebSocket broadcast or subscribe call.
manager = ConnectionManager()
