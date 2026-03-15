"""AI-assisted endpoints for mind map analysis.

URLs
────
  POST /api/mindmaps/{map_id}/suggest-relationships
  GET  /api/mindmaps/{map_id}/clusters
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.graph import Edge, MindMap, Node
from services.ai_service import cluster_nodes, suggest_relationships

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
