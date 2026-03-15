"""SQLAlchemy ORM models for the MindMap Live graph data model.

All four core entities — User, MindMap, MapMember, Node, Edge — are defined
here in a single module so that SQLAlchemy can resolve all foreign-key and
relationship back-references without circular-import issues.

Schema rationale: docs/ARCHITECTURE.md § 2 "Graph Data Model".
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────


class MapRole(str, enum.Enum):
    """Access roles for map membership.

    Stored as a native PostgreSQL ENUM type (``map_role``).
    """

    owner = "owner"
    editor = "editor"
    viewer = "viewer"


# ── Models ────────────────────────────────────────────────────────────────────


class User(Base):
    """Authenticated user account.

    Email is normalised to lowercase before insert and is the unique
    identifier used for authentication lookups.
    """

    __tablename__ = "users"
    __table_args__ = (Index("idx_users_email", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    owned_maps: Mapped[list["MindMap"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    map_memberships: Mapped[list["MapMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class MindMap(Base):
    """A named workspace containing a knowledge graph.

    Deleting a map cascades to all of its nodes, edges, and memberships.
    """

    __tablename__ = "maps"
    __table_args__ = (Index("idx_maps_owner", "owner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        back_populates="owned_maps",
        lazy="raise",
    )
    members: Mapped[list["MapMember"]] = relationship(
        back_populates="map",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    nodes: Mapped[list["Node"]] = relationship(
        back_populates="map",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    edges: Mapped[list["Edge"]] = relationship(
        back_populates="map",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class MapMember(Base):
    """Join table for map access control (users ↔ maps).

    The owner is also inserted here as ``role = MapRole.owner`` when a
    map is created, so a single query on ``map_members`` can determine
    all access without joining ``maps.owner_id``.
    """

    __tablename__ = "map_members"
    __table_args__ = (Index("idx_map_members_user", "user_id"),)

    map_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maps.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[MapRole] = mapped_column(
        SAEnum(MapRole, name="map_role", create_type=False),
        nullable=False,
        default=MapRole.viewer,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    map: Mapped["MindMap"] = relationship(back_populates="members", lazy="raise")
    user: Mapped["User"] = relationship(back_populates="map_memberships", lazy="raise")


class Node(Base):
    """A single concept or idea on the canvas.

    Position (x, y) is stored as logical canvas coordinates. The client
    is responsible for viewport-to-canvas transformation.

    Deleting a node cascades to all edges where it is source or target.
    """

    __tablename__ = "nodes"
    __table_args__ = (
        # Primary access pattern: fetch all nodes for a map.
        Index("idx_nodes_map", "map_id"),
        # Supports paginated timeline views ordered newest-first within a map.
        Index("idx_nodes_created", "map_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    map_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maps.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Hex colour string, e.g. "#6366f1". Validated to #RRGGBB format in schemas.
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, server_default=text("'#6366f1'")
    )
    # Semantic type of the node. One of: idea, decision, question, note.
    node_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'idea'")
    )
    x: Mapped[float] = mapped_column(
        Double(), nullable=False, server_default=text("0")
    )
    y: Mapped[float] = mapped_column(
        Double(), nullable=False, server_default=text("0")
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    map: Mapped["MindMap"] = relationship(back_populates="nodes", lazy="raise")
    creator: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by], lazy="raise"
    )


class Edge(Base):
    """A directed relationship between two nodes in the same map.

    Database-level constraints:
    - ``no_self_loops``: source_id != target_id.
    - ``unique_directed_edge``: only one directed edge between any two nodes
      per map. The reverse direction (B→A) is a separate, allowed edge.
    """

    __tablename__ = "edges"
    __table_args__ = (
        CheckConstraint("source_id <> target_id", name="no_self_loops"),
        UniqueConstraint(
            "map_id", "source_id", "target_id", name="unique_directed_edge"
        ),
        # Primary access pattern: fetch all edges for a map.
        Index("idx_edges_map", "map_id"),
        # Neighbour-lookup: edges leaving a node.
        Index("idx_edges_source", "source_id"),
        # Neighbour-lookup: edges arriving at a node.
        Index("idx_edges_target", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Denormalised from source/target for fast map-scoped queries.
    map_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maps.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    map: Mapped["MindMap"] = relationship(back_populates="edges", lazy="raise")
    source: Mapped["Node"] = relationship(foreign_keys=[source_id], lazy="raise")
    target: Mapped["Node"] = relationship(foreign_keys=[target_id], lazy="raise")
    creator: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by], lazy="raise"
    )
