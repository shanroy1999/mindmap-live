"""Pydantic schemas for user request/response validation."""

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Shared user fields."""

    email: EmailStr
    display_name: str


class UserCreate(UserBase):
    """Schema for registering a new user."""

    password: str


class UserRead(UserBase):
    """Schema for reading a user — excludes sensitive fields like password."""

    id: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
