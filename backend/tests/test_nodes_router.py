"""Happy-path tests for /api/nodes — update and delete by node ID."""

from httpx import AsyncClient


class TestNodesRouter:
    async def test_update_node(
        self, async_client: AsyncClient, make_user, make_map, make_node
    ) -> None:
        """PATCH /{node_id} applies partial updates and returns the updated node."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap, label="Old Label", x=0.0, y=0.0)
        resp = await async_client.patch(
            f"/api/nodes/{node.id}",
            json={"label": "New Label", "x": 42.5, "y": 99.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "New Label"
        assert data["x"] == 42.5
        assert data["y"] == 99.0
        assert data["id"] == str(node.id)

    async def test_delete_node(
        self, async_client: AsyncClient, make_user, make_map, make_node
    ) -> None:
        """DELETE /{node_id} returns 204."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap)
        resp = await async_client.delete(f"/api/nodes/{node.id}")
        assert resp.status_code == 204
