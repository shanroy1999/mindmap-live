"""Business logic for edge operations."""

from typing import Optional

from sqlalchemy.orm import Session

from models.edge import Edge
from schemas.edge import EdgeCreate, EdgeUpdate


def get_all(db: Session) -> list[Edge]:
    """Return all edges from the database."""
    return db.query(Edge).all()


def get_by_id(db: Session, edge_id: str) -> Optional[Edge]:
    """Return a single edge by its ID, or None if not found."""
    return db.query(Edge).filter(Edge.id == edge_id).first()


def create(db: Session, payload: EdgeCreate) -> Edge:
    """Create and persist a new edge."""
    edge = Edge(**payload.model_dump())
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


def update(db: Session, edge_id: str, payload: EdgeUpdate) -> Optional[Edge]:
    """Apply a partial update to an existing edge.

    Returns the updated edge, or None if the edge was not found.
    """
    edge = get_by_id(db, edge_id)
    if edge is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(edge, field, value)
    db.commit()
    db.refresh(edge)
    return edge


def delete(db: Session, edge_id: str) -> bool:
    """Delete an edge by ID.

    Returns True if the edge was deleted, False if it was not found.
    """
    edge = get_by_id(db, edge_id)
    if edge is None:
        return False
    db.delete(edge)
    db.commit()
    return True
