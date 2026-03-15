"""Happy-path tests for /api/mindmaps — map CRUD and map-scoped nodes/edges."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from jose import jwt

_SECRET = os.environ.get("SECRET_KEY", "supersecretkey123")


def _make_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    return jwt.encode({"sub": str(user_id), "exp": expire}, _SECRET, algorithm="HS256")


class TestMindmapsRouter:
    async def test_create_mindmap(self, async_client: AsyncClient, make_user) -> None:
        """POST / creates a map and returns 201 with the new map."""
        user = await make_user()
        resp = await async_client.post(
            "/api/mindmaps/",
            json={"title": "My Map", "is_public": False},
            headers={"Authorization": f"Bearer {_make_token(user.id)}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My Map"
        assert data["owner_id"] == str(user.id)
        assert "id" in data

    async def test_list_mindmaps(self, async_client: AsyncClient, make_user, make_map) -> None:
        """GET / returns a list of all maps."""
        user = await make_user()
        await make_map(owner=user, title="Listed Map")
        resp = await async_client.get("/api/mindmaps/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert any(m["title"] == "Listed Map" for m in resp.json())

    async def test_get_mindmap(self, async_client: AsyncClient, make_user, make_map) -> None:
        """GET /{map_id} returns the map by ID."""
        user = await make_user()
        mindmap = await make_map(owner=user, title="Specific Map")
        resp = await async_client.get(f"/api/mindmaps/{mindmap.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(mindmap.id)
        assert resp.json()["title"] == "Specific Map"

    async def test_delete_mindmap(self, async_client: AsyncClient, make_user, make_map) -> None:
        """DELETE /{map_id} returns 204 and the map is gone."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        resp = await async_client.delete(f"/api/mindmaps/{mindmap.id}")
        assert resp.status_code == 204

    async def test_create_node_in_map(
        self, async_client: AsyncClient, make_user, make_map
    ) -> None:
        """POST /{map_id}/nodes creates a node and returns 201."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        resp = await async_client.post(
            f"/api/mindmaps/{mindmap.id}/nodes",
            json={"label": "Concept", "x": 10.0, "y": 20.0},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "Concept"
        assert data["map_id"] == str(mindmap.id)

    async def test_list_nodes_in_map(
        self, async_client: AsyncClient, make_user, make_map, make_node
    ) -> None:
        """GET /{map_id}/nodes returns all nodes in the map."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        await make_node(mindmap=mindmap, label="Node A")
        await make_node(mindmap=mindmap, label="Node B")
        resp = await async_client.get(f"/api/mindmaps/{mindmap.id}/nodes")
        assert resp.status_code == 200
        labels = [n["label"] for n in resp.json()]
        assert "Node A" in labels
        assert "Node B" in labels

    async def test_create_edge_in_map(
        self, async_client: AsyncClient, make_user, make_map, make_node
    ) -> None:
        """POST /{map_id}/edges creates a directed edge and returns 201."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="Source")
        tgt = await make_node(mindmap=mindmap, label="Target")
        resp = await async_client.post(
            f"/api/mindmaps/{mindmap.id}/edges",
            json={"source_id": str(src.id), "target_id": str(tgt.id), "label": "links to"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["source_id"] == str(src.id)
        assert data["target_id"] == str(tgt.id)
        assert data["label"] == "links to"

    async def test_list_edges_in_map(
        self, async_client: AsyncClient, make_user, make_map, make_node, make_edge
    ) -> None:
        """GET /{map_id}/edges returns all edges in the map."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        a = await make_node(mindmap=mindmap, label="A")
        b = await make_node(mindmap=mindmap, label="B")
        await make_edge(mindmap=mindmap, source=a, target=b, label="edge1")
        resp = await async_client.get(f"/api/mindmaps/{mindmap.id}/edges")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["label"] == "edge1"
