"""Happy-path tests for /api/users — register and get."""

import uuid

from httpx import AsyncClient


class TestUsersRouter:
    async def test_register_creates_user(self, async_client: AsyncClient) -> None:
        """POST / with valid data returns 201 and the new user's profile."""
        unique_email = f"newuser-{uuid.uuid4().hex[:8]}@example.com"
        resp = await async_client.post(
            "/api/users/",
            json={
                "email": unique_email,
                "display_name": "New User",
                "password": "securepass",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == unique_email
        assert data["display_name"] == "New User"
        assert "id" in data
        assert "hashed_password" not in data

    async def test_get_user_returns_profile(self, async_client: AsyncClient, make_user) -> None:
        """GET /{user_id} returns the user's public profile."""
        user = await make_user(email="fetched@example.com", display_name="Fetched")
        resp = await async_client.get(f"/api/users/{user.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(user.id)
        assert data["email"] == "fetched@example.com"
