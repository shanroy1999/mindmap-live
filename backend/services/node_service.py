"""Business logic for node operations."""

from sqlalchemy.orm import Session

from models.node import Node
from schemas.node import NodeCreate, NodeUpdate


def get_all(db: Session) -> list[Node]:
    """Return all nodes from the database."""
    return db.query(Node).all()


def get_by_id(db: Session, node_id: str) -> Node | None:
    """Return a single node by its ID, or None if not found."""
    return db.query(Node).filter(Node.id == node_id).first()


def create(db: Session, payload: NodeCreate) -> Node:
    """Create and persist a new node."""
    node = Node(**payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def update(db: Session, node_id: str, payload: NodeUpdate) -> Node | None:
    """Apply a partial update to an existing node.

    Returns the updated node, or None if the node was not found.
    """
    node = get_by_id(db, node_id)
    if node is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return node


def delete(db: Session, node_id: str) -> bool:
    """Delete a node by ID.

    Returns True if the node was deleted, False if it was not found.
    """
    node = get_by_id(db, node_id)
    if node is None:
        return False
    db.delete(node)
    db.commit()
    return True
