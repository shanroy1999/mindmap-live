"""Pydantic v2 schemas for all MindMap Live models.

Naming convention:
  <Entity>Create   — fields accepted when creating a new record
  <Entity>Update   — fields accepted for partial updates (all optional)
  <Entity>Read     — fields returned to API clients (server-generated fields included)

UUID fields are serialised as strings in JSON automatically by Pydantic v2.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from models.graph import MapRole


# ── Auth ──────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Credentials payload for POST /api/auth/login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token envelope returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")


# ── User ──────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    """Fields required to register a new user account."""

    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, description="Plain-text password; hashed before storage")


class UserRead(BaseModel):
    """Public-safe user representation — hashed_password is never included."""

    id: uuid.UUID
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Fields a user may change on their own account."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=8)


# ── MindMap ───────────────────────────────────────────────────────────────────


class MindMapCreate(BaseModel):
    """Fields required to create a new map workspace."""

    owner_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    is_public: bool = False


class MindMapRead(BaseModel):
    """Map representation returned to clients."""

    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: Optional[str]
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MindMapWithRole(MindMapRead):
    """MindMapRead extended with the requesting user's membership role.

    Used for list endpoints where the caller needs to know their own
    permission level without a separate membership lookup.
    """

    role: MapRole


class MindMapUpdate(BaseModel):
    """Fields that may be updated on an existing map."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    is_public: Optional[bool] = None


# ── Map membership ────────────────────────────────────────────────────────────


class MapMemberCreate(BaseModel):
    """Payload for inviting a user to a map."""

    user_id: uuid.UUID
    role: MapRole = MapRole.viewer


class MapMemberRead(BaseModel):
    """Map membership record with nested user details."""

    map_id: uuid.UUID
    user_id: uuid.UUID
    role: MapRole
    joined_at: datetime
    user: UserRead

    model_config = {"from_attributes": True}


class MapMemberUpdate(BaseModel):
    """Payload for changing an existing member's role."""

    role: MapRole


# ── Node ──────────────────────────────────────────────────────────────────────


class NodeCreate(BaseModel):
    """Fields required to place a new node on the canvas."""

    label: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    color: str = Field(
        "#6366f1",
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="Hex colour code, e.g. #6366f1",
    )
    x: float = Field(0.0, description="Canvas x-coordinate in logical pixels")
    y: float = Field(0.0, description="Canvas y-coordinate in logical pixels")


class NodeRead(BaseModel):
    """Node representation returned to clients."""

    id: uuid.UUID
    map_id: uuid.UUID
    label: str
    description: Optional[str]
    color: str
    x: float
    y: float
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NodeUpdate(BaseModel):
    """Partial update fields for a node — all optional."""

    label: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    x: Optional[float] = None
    y: Optional[float] = None


# ── Edge ──────────────────────────────────────────────────────────────────────


class EdgeCreate(BaseModel):
    """Fields required to draw a new directed edge between two nodes."""

    source_id: uuid.UUID
    target_id: uuid.UUID
    label: Optional[str] = None

    def validate_no_self_loop(self) -> None:
        """Raise ValueError if source and target are the same node."""
        if self.source_id == self.target_id:
            raise ValueError("source_id and target_id must be different nodes")


class EdgeRead(BaseModel):
    """Edge representation returned to clients."""

    id: uuid.UUID
    map_id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    label: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class EdgeUpdate(BaseModel):
    """Partial update fields for an edge."""

    label: Optional[str] = None


# ── WebSocket ─────────────────────────────────────────────────────────────────


class WsEvent(BaseModel):
    """Envelope for all WebSocket broadcast messages.

    ``payload`` is the full serialised object for create/update events,
    or ``{"id": "<uuid>"}`` for delete events.

    See docs/ARCHITECTURE.md § 5 for the full event type table.
    """

    type: str = Field(
        ...,
        examples=[
            "node:created",
            "node:updated",
            "node:deleted",
            "edge:created",
            "edge:deleted",
            "member:joined",
        ],
    )
    map_id: uuid.UUID
    actor_id: uuid.UUID
    payload: Any
