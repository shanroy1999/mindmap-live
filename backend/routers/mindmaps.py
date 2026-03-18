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
from models.graph import Edge, MapMember, MindMap, Node, User
from routers.auth import get_current_user
from schemas.graph import (
    EdgeCreate,
    EdgeRead,
    MindMapCreate,
    MindMapListResponse,
    MindMapRead,
    MindMapUpdate,
    NodeCreate,
    NodeRead,
    SharedMindMapRead,
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
    response_model=MindMapListResponse,
    summary="List mind maps visible to the current user",
    responses={
        401: {"description": "Token is missing or invalid"},
    },
)
async def list_mindmaps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MindMapListResponse:
    """Return maps split into owned and shared, newest first within each group.

    * ``my_maps`` — maps where ``owner_id`` matches the current user.
    * ``shared_with_me`` — public maps where the user has a ``map_members`` row
      but is **not** the owner, including the owner's display name.
    """
    # Maps owned by the current user.
    my_result = await db.execute(
        select(MindMap)
        .where(MindMap.owner_id == current_user.id)
        .order_by(MindMap.created_at.desc())
    )
    my_maps = [MindMapRead.model_validate(m) for m in my_result.scalars().all()]

    # Public maps the user has been added to as a member (not their own maps).
    shared_result = await db.execute(
        select(MindMap, User.display_name)
        .join(MapMember, MapMember.map_id == MindMap.id)
        .join(User, User.id == MindMap.owner_id)
        .where(
            MapMember.user_id == current_user.id,
            MindMap.owner_id != current_user.id,
            MindMap.is_public.is_(True),
        )
        .order_by(MindMap.created_at.desc())
    )
    shared_maps = [
        SharedMindMapRead(
            **MindMapRead.model_validate(m).model_dump(),
            owner_display_name=display_name,
        )
        for m, display_name in shared_result.all()
    ]

    return MindMapListResponse(my_maps=my_maps, shared_with_me=shared_maps)


@router.get(
    "/{map_id}",
    response_model=MindMapRead,
    summary="Get a single mind map",
    responses={
        403: {"description": "Map is private and the requesting user is not the owner"},
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — map_id is not a valid UUID"},
    },
)
async def get_mindmap(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MindMap:
    """Return a single mind map by ID.

    Access is granted when the requesting user is the owner **or** the map has
    ``is_public=True``.  Private maps owned by someone else return **403**.
    """
    mindmap = await _get_map_or_404(map_id, db)
    if mindmap.owner_id != current_user.id and not mindmap.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This map is private",
        )
    return mindmap


@router.patch(
    "/{map_id}",
    response_model=MindMapRead,
    summary="Update a mind map",
    responses={
        403: {"description": "Only the map owner can update this map"},
        404: {"description": "MindMap not found"},
        422: {"description": "Validation error — invalid body or map_id"},
    },
)
async def update_mindmap(
    map_id: uuid.UUID,
    payload: MindMapUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MindMap:
    """Apply a partial update (title, description, is_public) to a mind map.

    Only the map owner may call this endpoint.
    """
    mindmap = await _get_map_or_404(map_id, db)
    if mindmap.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the map owner can update this map",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mindmap, field, value)
    await db.commit()
    await db.refresh(mindmap)
    return mindmap


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
        node_type=payload.node_type,
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
