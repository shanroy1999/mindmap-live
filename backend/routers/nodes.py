"""Router for node CRUD operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.database import get_db
from schemas.node import NodeCreate, NodeRead, NodeUpdate
from services import node_service

router = APIRouter()


@router.get("/", response_model=list[NodeRead])
def list_nodes(db: Session = Depends(get_db)) -> list[NodeRead]:
    """Return all nodes."""
    return node_service.get_all(db)


@router.post("/", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)) -> NodeRead:
    """Create and return a new node."""
    return node_service.create(db, payload)


@router.get("/{node_id}", response_model=NodeRead)
def get_node(node_id: str, db: Session = Depends(get_db)) -> NodeRead:
    """Return a single node by ID."""
    node = node_service.get_by_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return node


@router.patch("/{node_id}", response_model=NodeRead)
def update_node(
    node_id: str, payload: NodeUpdate, db: Session = Depends(get_db)
) -> NodeRead:
    """Apply a partial update to a node and return the updated record."""
    node = node_service.update(db, node_id, payload)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return node


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a node by ID."""
    deleted = node_service.delete(db, node_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
