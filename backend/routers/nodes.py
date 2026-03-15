"""Node update and delete endpoints (resource-scoped by node ID).

Map-scoped node operations (create, list) live in routers/mindmaps.py.

URL structure
─────────────
  PATCH  /api/nodes/{node_id}   update label, description, color, or position
  DELETE /api/nodes/{node_id}   delete a node and all edges that reference it
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.graph import Node
from schemas.graph import NodeRead, NodeUpdate

router = APIRouter()


@router.patch(
    "/{node_id}",
    response_model=NodeRead,
    summary="Update a node",
    responses={
        404: {"description": "Node not found"},
        422: {"description": "Validation error — invalid body or node_id"},
    },
)
async def update_node(
    node_id: uuid.UUID,
    payload: NodeUpdate,
    db: AsyncSession = Depends(get_db),
) -> Node:
    """Apply a partial update to a node.

    Only fields present in the request body are modified; omitted fields
    are left unchanged.  Returns the updated node.
    """
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, field, value)

    await db.commit()
    await db.refresh(node)
    return node


@router.delete(
    "/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a node",
    responses={
        404: {"description": "Node not found"},
        422: {"description": "Validation error — node_id is not a valid UUID"},
    },
)
async def delete_node(
    node_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a node.

    All edges that reference this node as source or target are removed
    automatically by the database ``ON DELETE CASCADE`` constraint.
    """
    result = await db.execute(select(Node.id).where(Node.id == node_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )

    await db.execute(sql_delete(Node).where(Node.id == node_id))
    await db.commit()
