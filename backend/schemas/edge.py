"""Pydantic schemas for edge request/response validation."""

from datetime import datetime

from typing import Optional

from pydantic import BaseModel


class EdgeBase(BaseModel):
    """Shared edge fields."""

    source_id: str
    target_id: str
    label: Optional[str] = None


class EdgeCreate(EdgeBase):
    """Schema for creating a new edge."""


class EdgeUpdate(BaseModel):
    """Schema for partial edge updates."""

    label: Optional[str] = None


class EdgeRead(EdgeBase):
    """Schema for reading an edge — includes server-generated fields."""

    id: str
    created_at: datetime

    model_config = {"from_attributes": True}
