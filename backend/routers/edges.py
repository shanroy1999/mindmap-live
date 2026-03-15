"""Edge delete endpoint (resource-scoped by edge ID).

Map-scoped edge operations (create, list) live in routers/mindmaps.py.

URL structure
─────────────
  DELETE /api/edges/{edge_id}   delete a single edge
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.graph import Edge

router = APIRouter()


@router.delete(
    "/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an edge",
    responses={
        404: {"description": "Edge not found"},
        422: {"description": "Validation error — edge_id is not a valid UUID"},
    },
)
async def delete_edge(
    edge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a directed edge by ID."""
    result = await db.execute(select(Edge.id).where(Edge.id == edge_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge {edge_id} not found",
        )

    await db.execute(sql_delete(Edge).where(Edge.id == edge_id))
    await db.commit()
