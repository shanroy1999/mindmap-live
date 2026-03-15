"""Pydantic schemas for node request/response validation."""

from datetime import datetime

from typing import Optional

from pydantic import BaseModel


class NodeBase(BaseModel):
    """Shared node fields."""

    label: str
    description: Optional[str] = None
    x: float = 0.0
    y: float = 0.0


class NodeCreate(NodeBase):
    """Schema for creating a new node."""


class NodeUpdate(BaseModel):
    """Schema for partial node updates (all fields optional)."""

    label: Optional[str] = None
    description: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None


class NodeRead(NodeBase):
    """Schema for reading a node — includes server-generated fields."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
