"""WebSocket endpoint for real-time map collaboration.

URL
───
  WS /ws/mindmaps/{mindmap_id}?token=<jwt>

The client must supply a valid JWT as the ``token`` query parameter because
browsers cannot set ``Authorization`` headers on WebSocket connections.
The server closes the socket with code 4001 (policy violation) if the token
is missing, invalid, or expired.

Message contract
────────────────
Both directions carry raw JSON objects — the server does not impose an
envelope schema here so the frontend can define event shapes freely.
Whatever JSON the client sends is broadcast verbatim to every other connection
on the same map (the sender is excluded).
"""

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from db.database import AsyncSessionLocal
from models.graph import User
from routers.auth import _ALGORITHM, _SECRET_KEY
from services.connection_manager import manager

router = APIRouter()

_WS_POLICY_VIOLATION = 4001  # custom close code: auth failure


async def _authenticate(token: str) -> Optional[User]:
    """Decode *token* and return the matching User, or None on any failure."""
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        user_id: str = payload.get("sub", "")
        if not user_id:
            return None
    except JWTError:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()


@router.websocket("/mindmaps/{mindmap_id}")
async def ws_mindmap(
    websocket: WebSocket,
    mindmap_id: uuid.UUID,
    token: str = "",
) -> None:
    """Join the real-time room for *mindmap_id*.

    Lifecycle:
    1. Authenticate via ``?token=`` query param — reject with 4001 if invalid.
    2. Accept the connection and register with ConnectionManager.
    3. Loop: receive JSON from this client, broadcast to all others on the map.
    4. On disconnect (clean or network error) remove from ConnectionManager.
    """
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=_WS_POLICY_VIOLATION)
        return

    await manager.connect(websocket, mindmap_id, user.id)

    # Start the Redis subscriber task for this room if one isn't already running.
    sub_task = manager.get_subscriber_task(mindmap_id)
    if sub_task is None or sub_task.done():
        sub_task = asyncio.create_task(
            manager.subscribe(mindmap_id),
            name=f"redis-sub:{mindmap_id}",
        )
        manager.set_subscriber_task(mindmap_id, sub_task)

    try:
        while True:
            message = await websocket.receive_json()
            await manager.broadcast(message, mindmap_id, exclude_websocket=websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, mindmap_id)
        # Cancel the subscriber only when the last client in the room has left.
        if manager.room_is_empty(mindmap_id):
            task = manager.pop_subscriber_task(mindmap_id)
            if task and not task.done():
                task.cancel()
