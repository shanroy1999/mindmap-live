"""Router for edge CRUD operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.database import get_db
from schemas.edge import EdgeCreate, EdgeRead, EdgeUpdate
from services import edge_service

router = APIRouter()


@router.get("/", response_model=list[EdgeRead])
def list_edges(db: Session = Depends(get_db)) -> list[EdgeRead]:
    """Return all edges."""
    return edge_service.get_all(db)


@router.post("/", response_model=EdgeRead, status_code=status.HTTP_201_CREATED)
def create_edge(payload: EdgeCreate, db: Session = Depends(get_db)) -> EdgeRead:
    """Create and return a new edge."""
    return edge_service.create(db, payload)


@router.get("/{edge_id}", response_model=EdgeRead)
def get_edge(edge_id: str, db: Session = Depends(get_db)) -> EdgeRead:
    """Return a single edge by ID."""
    edge = edge_service.get_by_id(db, edge_id)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")
    return edge


@router.patch("/{edge_id}", response_model=EdgeRead)
def update_edge(
    edge_id: str, payload: EdgeUpdate, db: Session = Depends(get_db)
) -> EdgeRead:
    """Apply a partial update to an edge and return the updated record."""
    edge = edge_service.update(db, edge_id, payload)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")
    return edge


@router.delete("/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge(edge_id: str, db: Session = Depends(get_db)) -> None:
    """Delete an edge by ID."""
    deleted = edge_service.delete(db, edge_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")
