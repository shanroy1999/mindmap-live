"""MindMap CRUD endpoints, plus map-scoped Node and Edge operations.

URL structure
─────────────
  POST   /api/mindmaps/                      create a mind map
  GET    /api/mindmaps/                      list all mind maps
  GET    /api/mindmaps/{map_id}              get one mind map
  DELETE /api/mindmaps/{map_id}              delete a mind map (cascades to nodes/edges)

  POST   /api/mindmaps/{map_id}/nodes        add a node to a map
  GET    /api/mindmaps/{map_id}/nodes        list all nodes in a map

  POST   /api/mindmaps/{map_id}/edges        add an edge to a map
  GET    /api/mindmaps/{map_id}/edges        list all edges in a map
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.graph import Edge, MindMap, Node, User
from routers.auth import get_current_user
from schemas.graph import (
    EdgeCreate,
    EdgeRead,
    MindMapCreate,
    MindMapRead,
    NodeCreate,
    NodeRead,
)

router = APIRouter()


# ── Shared helper ─────────────────────────────────────────────────────────────


async def _get_map_or_404(map_id: uuid.UUID, db: AsyncSession) -> MindMap:
    """Return the MindMap row or raise HTTP 404."""
    result = await db.execute(select(MindMap).where(MindMap.id == map_id))
    mindmap = result.scalar_one_or_none()
    if mindmap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MindMap {map_id} not found",
        )
    return mindmap


# ── MindMap CRUD ──────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=MindMapRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new mind map",
    responses={422: {"description": "Validation error — invalid request body"}},
)
async def create_mindmap(
    payload: MindMapCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MindMap:
    """Create a mind map owned by the authenticated user."""
    mindmap = MindMap(
        owner_id=current_user.id,
        title=payload.title,
        description=payload.description,
        is_public=payload.is_public,
    )
    db.add(mindmap)
    await db.commit()
    await db.refresh(mindmap)
    return mindmap


@router.get(
    "/",
    response_model=List[MindMapRead],
    summary="List all mind maps",
)
async def list_mindmaps(db: AsyncSession = Depends(get_db)) -> List[MindMap]:
    """Return every mind map, newest first."""
    result = await db.execute(select(MindMap).order_by(MindMap.created_at.desc()))
    return list(result.scalars().all())


@router.get(
    "/{map_id}",
    response_model=MindMapRead,
    summary="Get a single mind map",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
    },
)
async def get_mindmap(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MindMap:
    """Return a single mind map by ID."""
    return await _get_map_or_404(map_id, db)


@router.delete(
    "/{map_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a mind map",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
    },
)
async def delete_mindmap(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a mind map and cascade-delete all its nodes and edges."""
    await _get_map_or_404(map_id, db)
    await db.execute(sql_delete(MindMap).where(MindMap.id == map_id))
    await db.commit()


# ── Nodes (map-scoped) ────────────────────────────────────────────────────────


@router.post(
    "/{map_id}/nodes",
    response_model=NodeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a node to a mind map",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — invalid body or map_id"},
    },
)
async def create_node(
    map_id: uuid.UUID,
    payload: NodeCreate,
    db: AsyncSession = Depends(get_db),
) -> Node:
    """Create a new node inside the specified mind map."""
    await _get_map_or_404(map_id, db)
    node = Node(
        map_id=map_id,
        label=payload.label,
        description=payload.description,
        color=payload.color,
        x=payload.x,
        y=payload.y,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.get(
    "/{map_id}/nodes",
    response_model=List[NodeRead],
    summary="List all nodes in a mind map",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
    },
)
async def list_nodes(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[Node]:
    """Return every node in the map, ordered by creation time."""
    await _get_map_or_404(map_id, db)
    result = await db.execute(
        select(Node).where(Node.map_id == map_id).order_by(Node.created_at)
    )
    return list(result.scalars().all())


# ── Edges (map-scoped) ────────────────────────────────────────────────────────


@router.post(
    "/{map_id}/edges",
    response_model=EdgeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an edge between two nodes in a mind map",
    responses={
        404: {"description": "MindMap or node not found in this map"},
        422: {"description": "Validation error — self-loop or invalid UUIDs"},
    },
)
async def create_edge(
    map_id: uuid.UUID,
    payload: EdgeCreate,
    db: AsyncSession = Depends(get_db),
) -> Edge:
    """Create a directed edge between ``source_id`` and ``target_id``.

    Returns **422** if source and target are the same node.
    Returns **404** if either node does not exist inside this map.
    """
    await _get_map_or_404(map_id, db)

    if payload.source_id == payload.target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_id and target_id must be different nodes",
        )

    for node_id, role in [(payload.source_id, "Source"), (payload.target_id, "Target")]:
        row = await db.execute(
            select(Node.id).where(Node.id == node_id, Node.map_id == map_id)
        )
        if row.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{role} node {node_id} not found in map {map_id}",
            )

    edge = Edge(
        map_id=map_id,
        source_id=payload.source_id,
        target_id=payload.target_id,
        label=payload.label,
    )
    db.add(edge)
    await db.commit()
    await db.refresh(edge)
    return edge


@router.get(
    "/{map_id}/edges",
    response_model=List[EdgeRead],
    summary="List all edges in a mind map",
    responses={
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
    },
)
async def list_edges(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[Edge]:
    """Return every edge in the map, ordered by creation time."""
    await _get_map_or_404(map_id, db)
    result = await db.execute(
        select(Edge).where(Edge.map_id == map_id).order_by(Edge.created_at)
    )
    return list(result.scalars().all())
