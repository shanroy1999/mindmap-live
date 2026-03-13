"""Pydantic schemas for node request/response validation."""

from datetime import datetime

from pydantic import BaseModel


class NodeBase(BaseModel):
    """Shared node fields."""

    label: str
    description: str | None = None
    x: float = 0.0
    y: float = 0.0


class NodeCreate(NodeBase):
    """Schema for creating a new node."""


class NodeUpdate(BaseModel):
    """Schema for partial node updates (all fields optional)."""

    label: str | None = None
    description: str | None = None
    x: float | None = None
    y: float | None = None


class NodeRead(NodeBase):
    """Schema for reading a node — includes server-generated fields."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
