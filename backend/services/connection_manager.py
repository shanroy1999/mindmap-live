"""WebSocket connection manager with Redis pub/sub.

Architecture
────────────
Each map room has one long-running ``subscribe`` task per process that listens
on the Redis channel ``mindmap:{map_id}`` and forwards messages to every local
WebSocket connection.

``broadcast`` publishes a JSON envelope to that channel.  The envelope carries
a ``_cid`` (connection ID) identifying the sender so the subscribe loop can
skip that connection, preserving the "no echo to sender" guarantee even though
delivery is now indirected through Redis.

This design scales horizontally: when multiple uvicorn workers run behind a
load balancer each worker has its own in-process room state.  A message
published by worker A is delivered to Redis and then forwarded by the subscribe
tasks running in ALL workers, so every connected client receives it regardless
of which worker accepted their WebSocket.
"""

import asyncio
import json
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import redis.asyncio as aioredis
from fastapi import WebSocket


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@dataclass
class _Connection:
    websocket: WebSocket
    user_id: uuid.UUID
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
    ) -> None:
        """Accept *websocket* and register it in the room.

        Task lifecycle (starting / stopping the Redis subscriber) is the
        responsibility of the caller (the WebSocket route handler).

        Args:
            websocket:  The incoming WebSocket connection to accept and track.
            mindmap_id: The map room this client is joining.
            user_id:    The authenticated user (stored for presence features).
        """
        await websocket.accept()
        key = str(mindmap_id)
        self._rooms[key].append(_Connection(websocket=websocket, user_id=user_id))

    async def disconnect(
        self,
        websocket: WebSocket,
        mindmap_id: uuid.UUID,
    ) -> None:
        """Remove *websocket* from the room.

        Cleans up the room dict when the last client leaves.  Task cancellation
        is the responsibility of the caller (the WebSocket route handler).

        Args:
            websocket:  The WebSocket that disconnected.
            mindmap_id: The map room the client was connected to.
        """
        key = str(mindmap_id)
        self._rooms[key] = [c for c in self._rooms[key] if c.websocket is not websocket]
        if not self._rooms[key]:
            del self._rooms[key]

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

    async def broadcast(
        self,
        message: dict,
        mindmap_id: uuid.UUID,
        exclude_websocket: Optional[WebSocket] = None,
    ) -> None:
        """Publish *message* to the Redis channel for *mindmap_id*.

        The message is wrapped in an envelope that carries the sender's
        connection ID so the subscribe loop can exclude them from delivery::

            {"_cid": "<sender-cid-or-null>", "data": {<original message>}}

        Args:
            message:           JSON-serialisable dict to broadcast.
            mindmap_id:        Target map room.
            exclude_websocket: The sending connection; its *cid* is embedded in
                               the envelope so the subscribe loop skips it.
        """
        key = str(mindmap_id)

        sender_cid: Optional[str] = None
        if exclude_websocket is not None:
            for conn in self._rooms.get(key, []):
                if conn.websocket is exclude_websocket:
                    sender_cid = conn.cid
                    break

        envelope = json.dumps({"_cid": sender_cid, "data": message})
        pub = await self._publisher()
        await pub.publish(f"mindmap:{key}", envelope)

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
                    data: dict = envelope["data"]
                except (json.JSONDecodeError, KeyError, TypeError):
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
