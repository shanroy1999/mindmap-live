"""Happy-path tests for /api/edges — delete by edge ID."""

from httpx import AsyncClient


class TestEdgesRouter:
    async def test_delete_edge(
        self, async_client: AsyncClient, make_user, make_map, make_node, make_edge
    ) -> None:
        """DELETE /{edge_id} returns 204."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="Src")
        tgt = await make_node(mindmap=mindmap, label="Tgt")
        edge = await make_edge(mindmap=mindmap, source=src, target=tgt)
        resp = await async_client.delete(f"/api/edges/{edge.id}")
        assert resp.status_code == 204
