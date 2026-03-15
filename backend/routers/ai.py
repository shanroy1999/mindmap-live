"""AI-assisted endpoints for mind map analysis.

URLs
────
  POST /api/mindmaps/{map_id}/suggest-relationships
  GET  /api/mindmaps/{map_id}/clusters
  POST /api/mindmaps/{map_id}/auto-layout
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.graph import Edge, MindMap, Node
from services.ai_service import auto_layout, cluster_nodes, suggest_relationships

router = APIRouter()


class RelationshipSuggestion(BaseModel):
    """A single relationship suggestion returned by Claude."""

    source_id: str
    target_id: str
    reason: str


@router.post(
    "/{map_id}/suggest-relationships",
    response_model=List[RelationshipSuggestion],
    summary="Suggest new relationships between nodes using Claude AI",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
        503: {"description": "AI service unavailable or returned unparseable output"},
    },
)
async def suggest_map_relationships(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[RelationshipSuggestion]:
    """Fetch all nodes and edges for *map_id*, then ask Claude to suggest
    up to 5 new relationships between nodes that don't already have an edge.

    The suggestions are returned as-is from the AI — the caller is responsible
    for deciding whether to persist them as actual edges.
    """
    result = await db.execute(select(MindMap).where(MindMap.id == map_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MindMap {map_id} not found",
        )

    nodes_result = await db.execute(select(Node).where(Node.map_id == map_id))
    nodes = [
        {"id": str(n.id), "label": n.label}
        for n in nodes_result.scalars().all()
    ]

    edges_result = await db.execute(select(Edge).where(Edge.map_id == map_id))
    existing_edges = [
        {"source_id": str(e.source_id), "target_id": str(e.target_id)}
        for e in edges_result.scalars().all()
    ]

    try:
        suggestions = await suggest_relationships(nodes, existing_edges)
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {exc}",
        ) from exc

    return [RelationshipSuggestion(**s) for s in suggestions]


class NodeCluster(BaseModel):
    """A semantic cluster of nodes returned by Claude."""

    cluster_name: str
    node_ids: List[str]


@router.get(
    "/{map_id}/clusters",
    response_model=List[NodeCluster],
    summary="Group map nodes into semantic clusters using Claude AI",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
        503: {"description": "AI service unavailable or returned unparseable output"},
    },
)
async def get_node_clusters(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[NodeCluster]:
    """Fetch all nodes for *map_id* and ask Claude to group them into
    semantic clusters based on their labels.
    """
    result = await db.execute(select(MindMap).where(MindMap.id == map_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MindMap {map_id} not found",
        )

    nodes_result = await db.execute(select(Node).where(Node.map_id == map_id))
    nodes = [
        {"id": str(n.id), "label": n.label}
        for n in nodes_result.scalars().all()
    ]

    try:
        clusters = await cluster_nodes(nodes)
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {exc}",
        ) from exc

    return [NodeCluster(**c) for c in clusters]


# ── Auto-layout ───────────────────────────────────────────────────────────────


class LayoutNode(BaseModel):
    """Position and hierarchy level for a single node in the auto-layout."""

    id: str
    x: float
    y: float
    level: int


class LayoutEdge(BaseModel):
    """A new edge suggested by the auto-layout analysis."""

    source_id: str
    target_id: str
    reason: str


class LayoutCluster(BaseModel):
    """A semantic grouping of nodes with an accent colour."""

    cluster_name: str
    node_ids: List[str]
    color: str


class AutoLayoutResponse(BaseModel):
    """Full layout plan returned by POST /auto-layout."""

    nodes: List[LayoutNode]
    edges_to_add: List[LayoutEdge]
    clusters: List[LayoutCluster]


@router.post(
    "/{map_id}/auto-layout",
    response_model=AutoLayoutResponse,
    summary="Compute a hierarchical auto-layout for a mind map using Claude AI",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
        503: {"description": "AI service unavailable or returned unparseable output"},
    },
)
async def auto_layout_map(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AutoLayoutResponse:
    """Fetch all nodes and edges for *map_id*, then ask Claude to:

    1. Determine the optimal hierarchy (root, children, siblings).
    2. Compute x/y coordinates for a clean tree layout — root at the top
       centre (x=0, y=0), children spread below with 200 px horizontal
       spacing and 150 px vertical spacing between levels.
    3. Suggest 2–4 new edges that would improve the graph's structure.
    4. Group nodes into 2–4 semantic clusters with distinct accent colours.

    The returned ``nodes`` list contains coordinates the frontend can apply
    directly via ``PATCH /api/nodes/{id}`` to reposition the canvas.
    """
    result = await db.execute(select(MindMap).where(MindMap.id == map_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MindMap {map_id} not found",
        )

    nodes_result = await db.execute(select(Node).where(Node.map_id == map_id))
    nodes = [
        {"id": str(n.id), "label": n.label, "node_type": n.node_type}
        for n in nodes_result.scalars().all()
    ]

    edges_result = await db.execute(select(Edge).where(Edge.map_id == map_id))
    existing_edges = [
        {"source_id": str(e.source_id), "target_id": str(e.target_id)}
        for e in edges_result.scalars().all()
    ]

    try:
        layout = await auto_layout(nodes, existing_edges)
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {exc}",
        ) from exc

    try:
        # clusters is intentionally empty — handled by the separate /clusters endpoint
        layout.setdefault("clusters", [])
        return AutoLayoutResponse(**layout)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI returned an unexpected layout structure: {exc}. Layout keys: {list(layout.keys())}",
        ) from exc
