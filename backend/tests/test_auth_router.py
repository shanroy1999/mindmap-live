"""Happy-path tests for /api/auth — login, refresh, me."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from jose import jwt
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_SECRET = os.environ.get("SECRET_KEY", "supersecretkey123")


def _make_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    return jwt.encode({"sub": str(user_id), "exp": expire}, _SECRET, algorithm="HS256")


class TestAuthRouter:
    async def test_login_returns_token(self, async_client: AsyncClient, make_user) -> None:
        """POST /login with valid credentials returns a signed JWT."""
        await make_user(email="login@example.com", hashed_password=_pwd.hash("password123"))
        resp = await async_client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600

    async def test_refresh_returns_new_token(self, async_client: AsyncClient, make_user) -> None:
        """POST /refresh with a valid token returns a fresh token."""
        user = await make_user()
        resp = await async_client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {_make_token(user.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_me_returns_user_profile(self, async_client: AsyncClient, make_user) -> None:
        """GET /me with a valid token returns the authenticated user's profile."""
        user = await make_user(email="me@example.com", display_name="MeUser")
        resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {_make_token(user.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(user.id)
        assert data["email"] == "me@example.com"
        assert data["display_name"] == "MeUser"
