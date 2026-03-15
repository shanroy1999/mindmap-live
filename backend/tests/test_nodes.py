"""Basic smoke tests for node and health endpoints using the async test client."""

import uuid

from httpx import AsyncClient


async def test_health_check(async_client: AsyncClient) -> None:
    """GET /health should return HTTP 200 with status ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_create_node_returns_201(
    async_client: AsyncClient, make_user, make_map
) -> None:
    """POST /api/mindmaps/{map_id}/nodes returns 201 with the created node."""
    user = await make_user()
    mindmap = await make_map(owner=user)
    response = await async_client.post(
        f"/api/mindmaps/{mindmap.id}/nodes",
        json={"label": "Test Node", "x": 100.0, "y": 200.0},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Test Node"
    assert "id" in data


async def test_list_nodes_returns_200(
    async_client: AsyncClient, make_user, make_map, make_node
) -> None:
    """GET /api/mindmaps/{map_id}/nodes returns 200 with a list."""
    user = await make_user()
    mindmap = await make_map(owner=user)
    await make_node(mindmap=mindmap, label="Test Node")
    response = await async_client.get(f"/api/mindmaps/{mindmap.id}/nodes")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_patch_nonexistent_node_returns_404(async_client: AsyncClient) -> None:
    """PATCH /api/nodes/{id} for an unknown UUID returns HTTP 404."""
    response = await async_client.patch(
        f"/api/nodes/{uuid.uuid4()}",
        json={"label": "whatever"},
    )
    assert response.status_code == 404


async def test_delete_nonexistent_node_returns_404(async_client: AsyncClient) -> None:
    """DELETE /api/nodes/{id} for an unknown UUID returns HTTP 404."""
    response = await async_client.delete(f"/api/nodes/{uuid.uuid4()}")
    assert response.status_code == 404
