"""Tests for the GET /health endpoint.

Covers:
* Happy-path: endpoint returns 200 with the expected JSON body.
* Response shape: both ``status`` and ``database`` keys are present.
* DB-unreachable path: endpoint returns 500 when ``AsyncSessionLocal`` raises
  ``OperationalError``.  The ``failing_client`` fixture (defined in conftest.py)
  patches ``main.AsyncSessionLocal`` with a mock that raises and uses
  ``raise_server_exceptions=False`` so that FastAPI's 500 is captured as an HTTP
  response rather than re-raised.
"""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Functional tests for GET /health."""

    async def test_returns_http_200(self, async_client: AsyncClient) -> None:
        """A healthy service must respond with HTTP 200 OK."""
        response = await async_client.get("/health")
        assert response.status_code == 200

    async def test_response_is_json(self, async_client: AsyncClient) -> None:
        """The response Content-Type must be application/json."""
        response = await async_client.get("/health")
        assert "application/json" in response.headers["content-type"]

    async def test_status_field_is_ok(self, async_client: AsyncClient) -> None:
        """Response body must contain ``{"status": "ok"}``."""
        response = await async_client.get("/health")
        data = response.json()
        assert data.get("status") == "ok"

    async def test_database_field_is_reachable(self, async_client: AsyncClient) -> None:
        """Response body must report the database as reachable."""
        response = await async_client.get("/health")
        data = response.json()
        assert data.get("database") == "reachable"

    async def test_response_contains_exactly_two_fields(
        self, async_client: AsyncClient
    ) -> None:
        """Response body must have exactly the two documented keys."""
        response = await async_client.get("/health")
        data = response.json()
        assert set(data.keys()) == {"status", "database"}

    async def test_db_unreachable_returns_500(self, failing_client: AsyncClient) -> None:
        """When the database raises ``OperationalError``, the endpoint must return 500."""
        response = await failing_client.get("/health")
        assert response.status_code == 500

    async def test_db_unreachable_does_not_expose_internals(
        self, failing_client: AsyncClient
    ) -> None:
        """A 500 response must not leak stack traces or connection strings."""
        response = await failing_client.get("/health")
        body = response.text
        # These strings must never appear in an error response sent to clients.
        assert "asyncpg" not in body
        assert "postgresql" not in body.lower()
        assert "Traceback" not in body

    async def test_endpoint_is_idempotent(self, async_client: AsyncClient) -> None:
        """Calling /health multiple times in sequence must always return 200."""
        for _ in range(3):
            response = await async_client.get("/health")
            assert response.status_code == 200

    async def test_method_not_allowed_for_post(self, async_client: AsyncClient) -> None:
        """POST /health must return 405 Method Not Allowed."""
        response = await async_client.post("/health")
        assert response.status_code == 405

    async def test_method_not_allowed_for_delete(self, async_client: AsyncClient) -> None:
        """DELETE /health must return 405 Method Not Allowed."""
        response = await async_client.delete("/health")
        assert response.status_code == 405
