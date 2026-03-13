"""Tests for the /api/nodes endpoints."""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check() -> None:
    """GET /health should return HTTP 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_nodes_returns_200() -> None:
    """GET /api/nodes/ should return HTTP 200 with a list."""
    response = client.get("/api/nodes/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_node_returns_201() -> None:
    """POST /api/nodes/ should return HTTP 201 with the created node."""
    payload = {"label": "Test Node", "x": 100.0, "y": 200.0}
    response = client.post("/api/nodes/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Test Node"
    assert "id" in data


def test_get_nonexistent_node_returns_404() -> None:
    """GET /api/nodes/{id} for an unknown ID should return HTTP 404."""
    response = client.get("/api/nodes/does-not-exist")
    assert response.status_code == 404


def test_delete_nonexistent_node_returns_404() -> None:
    """DELETE /api/nodes/{id} for an unknown ID should return HTTP 404."""
    response = client.delete("/api/nodes/does-not-exist")
    assert response.status_code == 404
