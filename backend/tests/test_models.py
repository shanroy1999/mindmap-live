"""ORM model tests for MindMap Live.

Each test class covers one model.  All tests run inside a SAVEPOINT transaction
(see conftest.py) that is rolled back after the function finishes, so no data
persists between tests.

Cascade-delete tests use SQLAlchemy bulk-SQL ``DELETE`` statements rather than
``session.delete(obj)`` to avoid triggering the ``lazy="raise"`` guard on
relationships — we want to test the *database-level* ``ON DELETE CASCADE``
behaviour that the schema defines.

After any test that provokes an ``IntegrityError``, call
``await db_session.rollback()`` to roll back to the savepoint so the session
is usable for subsequent assertions in the same function.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.graph import Edge, MapMember, MapRole, MindMap, Node, User
from schemas.graph import (
    EdgeCreate,
    NodeCreate,
    NodeUpdate,
    UserCreate,
)


# ── User ──────────────────────────────────────────────────────────────────────


class TestUserModel:
    """Tests for the ``users`` table."""

    async def test_id_is_a_uuid(self, make_user) -> None:
        """Server-generated id must be a valid UUID."""
        user = await make_user()
        assert isinstance(user.id, uuid.UUID)

    async def test_all_fields_are_persisted(self, db_session: AsyncSession, make_user) -> None:
        """All supplied field values must be retrievable after a flush."""
        user = await make_user(
            email="bob@example.com",
            display_name="Bob",
            hashed_password="s3cr3t_hash",
        )
        # Reload from the database to confirm the row was written.
        result = await db_session.execute(select(User).where(User.id == user.id))
        loaded = result.scalar_one()
        assert loaded.email == "bob@example.com"
        assert loaded.display_name == "Bob"
        assert loaded.hashed_password == "s3cr3t_hash"

    async def test_is_active_defaults_to_true(self, make_user) -> None:
        """``is_active`` must default to True when not explicitly provided."""
        user = await make_user()
        assert user.is_active is True

    async def test_created_at_is_timezone_aware(self, make_user) -> None:
        """``created_at`` must be a timezone-aware datetime (TIMESTAMPTZ)."""
        user = await make_user()
        assert isinstance(user.created_at, datetime)
        assert user.created_at.tzinfo is not None

    async def test_email_uniqueness_constraint(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Inserting two users with the same email must raise ``IntegrityError``."""
        await make_user(email="dup@example.com")
        with pytest.raises(IntegrityError, match="users"):
            await make_user(email="dup@example.com")
        # Recover the session after the constraint violation.
        await db_session.rollback()

    async def test_inactive_user_can_be_created(self, make_user) -> None:
        """A user with ``is_active=False`` must be stored correctly."""
        user = await make_user(is_active=False)
        assert user.is_active is False


# ── MindMap ───────────────────────────────────────────────────────────────────


class TestMindMapModel:
    """Tests for the ``maps`` table."""

    async def test_id_is_a_uuid(self, make_user, make_map) -> None:
        """Server-generated id must be a valid UUID."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        assert isinstance(mindmap.id, uuid.UUID)

    async def test_all_fields_are_persisted(
        self, db_session: AsyncSession, make_user, make_map
    ) -> None:
        """Title, description, owner_id, and is_public must be stored."""
        user = await make_user()
        mindmap = await make_map(
            owner=user,
            title="My Knowledge Base",
            description="A test map",
            is_public=True,
        )
        result = await db_session.execute(select(MindMap).where(MindMap.id == mindmap.id))
        loaded = result.scalar_one()
        assert loaded.title == "My Knowledge Base"
        assert loaded.description == "A test map"
        assert loaded.owner_id == user.id
        assert loaded.is_public is True

    async def test_is_public_defaults_to_false(self, make_user, make_map) -> None:
        """``is_public`` must default to False."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        assert mindmap.is_public is False

    async def test_description_is_nullable(self, make_user, make_map) -> None:
        """A map may be created without a description."""
        user = await make_user()
        mindmap = await make_map(owner=user, description=None)
        assert mindmap.description is None

    async def test_both_timestamps_are_set(self, make_user, make_map) -> None:
        """``created_at`` and ``updated_at`` must be populated after flush."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        assert mindmap.created_at is not None
        assert mindmap.updated_at is not None
        assert mindmap.created_at.tzinfo is not None

    async def test_cascade_delete_removes_map_when_owner_deleted(
        self, db_session: AsyncSession, make_user, make_map
    ) -> None:
        """Deleting the owning user must cascade-delete their maps (ON DELETE CASCADE)."""
        user = await make_user(email="to_delete@example.com")
        mindmap = await make_map(owner=user)
        map_id = mindmap.id

        # Use bulk SQL DELETE to avoid the lazy="raise" guard on relationships.
        from sqlalchemy import delete as sa_delete

        await db_session.execute(sa_delete(User).where(User.id == user.id))
        await db_session.flush()

        result = await db_session.execute(select(MindMap).where(MindMap.id == map_id))
        assert result.scalar_one_or_none() is None


# ── MapMember ─────────────────────────────────────────────────────────────────


class TestMapMemberModel:
    """Tests for the ``map_members`` join table."""

    async def test_membership_is_created(
        self, db_session: AsyncSession, make_user, make_map
    ) -> None:
        """A membership row must be stored with the correct foreign keys."""
        owner = await make_user(email="owner@example.com")
        member = await make_user(email="member@example.com")
        mindmap = await make_map(owner=owner)

        membership = MapMember(
            map_id=mindmap.id,
            user_id=member.id,
            role=MapRole.editor,
        )
        db_session.add(membership)
        await db_session.flush()

        result = await db_session.execute(
            select(MapMember).where(
                MapMember.map_id == mindmap.id,
                MapMember.user_id == member.id,
            )
        )
        loaded = result.scalar_one()
        assert loaded.role == MapRole.editor
        assert loaded.joined_at is not None

    async def test_default_role_is_viewer(
        self, db_session: AsyncSession, make_user, make_map
    ) -> None:
        """Role must default to ``MapRole.viewer`` when not supplied."""
        owner = await make_user(email="owner2@example.com")
        member = await make_user(email="viewer@example.com")
        mindmap = await make_map(owner=owner)

        membership = MapMember(map_id=mindmap.id, user_id=member.id)
        db_session.add(membership)
        await db_session.flush()

        assert membership.role == MapRole.viewer

    async def test_duplicate_membership_raises(
        self, db_session: AsyncSession, make_user, make_map
    ) -> None:
        """The composite PK (map_id, user_id) prevents duplicate memberships."""
        owner = await make_user(email="owner3@example.com")
        member = await make_user(email="dup_member@example.com")
        mindmap = await make_map(owner=owner)

        db_session.add(MapMember(map_id=mindmap.id, user_id=member.id, role=MapRole.viewer))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(
                MapMember(map_id=mindmap.id, user_id=member.id, role=MapRole.editor)
            )
            await db_session.flush()
        await db_session.rollback()

    async def test_cascade_delete_removes_membership_when_map_deleted(
        self, db_session: AsyncSession, make_user, make_map
    ) -> None:
        """Deleting a map must remove all its membership rows."""
        from sqlalchemy import delete as sa_delete

        owner = await make_user(email="owner4@example.com")
        member = await make_user(email="cascaded_member@example.com")
        mindmap = await make_map(owner=owner)
        map_id = mindmap.id

        db_session.add(MapMember(map_id=map_id, user_id=member.id))
        await db_session.flush()

        await db_session.execute(sa_delete(MindMap).where(MindMap.id == map_id))
        await db_session.flush()

        result = await db_session.execute(
            select(MapMember).where(MapMember.map_id == map_id)
        )
        assert result.scalars().all() == []


# ── Node ──────────────────────────────────────────────────────────────────────


class TestNodeModel:
    """Tests for the ``nodes`` table."""

    async def test_id_is_a_uuid(self, make_user, make_map, make_node) -> None:
        """Server-generated id must be a valid UUID."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap)
        assert isinstance(node.id, uuid.UUID)

    async def test_all_fields_are_persisted(
        self, db_session: AsyncSession, make_user, make_map, make_node
    ) -> None:
        """All supplied field values must round-trip correctly."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(
            mindmap=mindmap,
            label="Machine Learning",
            description="A broad AI subfield",
            color="#ff0000",
            x=120.5,
            y=300.0,
        )
        result = await db_session.execute(select(Node).where(Node.id == node.id))
        loaded = result.scalar_one()
        assert loaded.label == "Machine Learning"
        assert loaded.description == "A broad AI subfield"
        assert loaded.color == "#ff0000"
        assert loaded.x == pytest.approx(120.5)
        assert loaded.y == pytest.approx(300.0)
        assert loaded.map_id == mindmap.id

    async def test_color_defaults_to_indigo(self, make_user, make_map, make_node) -> None:
        """Default color must be '#6366f1' (Tailwind indigo-500)."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap, color="#6366f1")
        assert node.color == "#6366f1"

    async def test_position_defaults_to_origin(
        self, make_user, make_map, make_node
    ) -> None:
        """x and y must default to 0.0 when not provided."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap, x=0.0, y=0.0)
        assert node.x == pytest.approx(0.0)
        assert node.y == pytest.approx(0.0)

    async def test_description_is_nullable(
        self, make_user, make_map, make_node
    ) -> None:
        """A node may be created without a description."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap, description=None)
        assert node.description is None

    async def test_timestamps_are_set(self, make_user, make_map, make_node) -> None:
        """Both timestamps must be populated and timezone-aware after flush."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap)
        assert node.created_at is not None
        assert node.updated_at is not None
        assert node.created_at.tzinfo is not None

    async def test_cascade_delete_removes_nodes_when_map_deleted(
        self, db_session: AsyncSession, make_user, make_map, make_node
    ) -> None:
        """Deleting a map must cascade-delete all its nodes."""
        from sqlalchemy import delete as sa_delete

        user = await make_user(email="node_cascade@example.com")
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap, label="Orphan")
        node_id = node.id

        await db_session.execute(sa_delete(MindMap).where(MindMap.id == mindmap.id))
        await db_session.flush()

        result = await db_session.execute(select(Node).where(Node.id == node_id))
        assert result.scalar_one_or_none() is None


# ── Edge ──────────────────────────────────────────────────────────────────────


class TestEdgeModel:
    """Tests for the ``edges`` table."""

    async def test_all_fields_are_persisted(
        self, db_session: AsyncSession, make_user, make_map, make_node, make_edge
    ) -> None:
        """All supplied field values must round-trip correctly."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="Source")
        tgt = await make_node(mindmap=mindmap, label="Target")
        edge = await make_edge(mindmap=mindmap, source=src, target=tgt, label="relates to")

        result = await db_session.execute(select(Edge).where(Edge.id == edge.id))
        loaded = result.scalar_one()
        assert loaded.source_id == src.id
        assert loaded.target_id == tgt.id
        assert loaded.label == "relates to"
        assert loaded.map_id == mindmap.id

    async def test_label_is_nullable(
        self, make_user, make_map, make_node, make_edge
    ) -> None:
        """An edge may be created without a label."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="A")
        tgt = await make_node(mindmap=mindmap, label="B")
        edge = await make_edge(mindmap=mindmap, source=src, target=tgt, label=None)
        assert edge.label is None

    async def test_no_self_loop_constraint(
        self, db_session: AsyncSession, make_user, make_map, make_node
    ) -> None:
        """An edge where source_id == target_id must be rejected by the DB."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        node = await make_node(mindmap=mindmap, label="Singleton")

        self_loop = Edge(
            map_id=mindmap.id,
            source_id=node.id,
            target_id=node.id,  # same node — violates no_self_loops constraint
        )
        db_session.add(self_loop)
        with pytest.raises(IntegrityError, match="no_self_loops"):
            await db_session.flush()
        await db_session.rollback()

    async def test_unique_directed_edge_constraint(
        self, db_session: AsyncSession, make_user, make_map, make_node, make_edge
    ) -> None:
        """A second identical directed edge in the same map must be rejected."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="P")
        tgt = await make_node(mindmap=mindmap, label="Q")
        await make_edge(mindmap=mindmap, source=src, target=tgt)

        duplicate = Edge(
            map_id=mindmap.id,
            source_id=src.id,
            target_id=tgt.id,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError, match="unique_directed_edge"):
            await db_session.flush()
        await db_session.rollback()

    async def test_reverse_direction_is_allowed(
        self, make_user, make_map, make_node, make_edge
    ) -> None:
        """A→B and B→A must both be valid (only duplicate directed edges are blocked)."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        a = await make_node(mindmap=mindmap, label="A")
        b = await make_node(mindmap=mindmap, label="B")
        edge_ab = await make_edge(mindmap=mindmap, source=a, target=b)
        edge_ba = await make_edge(mindmap=mindmap, source=b, target=a)

        assert edge_ab.source_id == a.id and edge_ab.target_id == b.id
        assert edge_ba.source_id == b.id and edge_ba.target_id == a.id

    async def test_cascade_delete_removes_edge_when_source_node_deleted(
        self, db_session: AsyncSession, make_user, make_map, make_node, make_edge
    ) -> None:
        """Deleting the source node must cascade-delete its outgoing edges."""
        from sqlalchemy import delete as sa_delete

        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="Src")
        tgt = await make_node(mindmap=mindmap, label="Tgt")
        edge = await make_edge(mindmap=mindmap, source=src, target=tgt)
        edge_id = edge.id

        await db_session.execute(sa_delete(Node).where(Node.id == src.id))
        await db_session.flush()

        result = await db_session.execute(select(Edge).where(Edge.id == edge_id))
        assert result.scalar_one_or_none() is None

    async def test_cascade_delete_removes_edge_when_target_node_deleted(
        self, db_session: AsyncSession, make_user, make_map, make_node, make_edge
    ) -> None:
        """Deleting the target node must also cascade-delete the edge."""
        from sqlalchemy import delete as sa_delete

        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="Source2")
        tgt = await make_node(mindmap=mindmap, label="Target2")
        edge = await make_edge(mindmap=mindmap, source=src, target=tgt)
        edge_id = edge.id

        await db_session.execute(sa_delete(Node).where(Node.id == tgt.id))
        await db_session.flush()

        result = await db_session.execute(select(Edge).where(Edge.id == edge_id))
        assert result.scalar_one_or_none() is None

    async def test_created_at_is_set(
        self, make_user, make_map, make_node, make_edge
    ) -> None:
        """``created_at`` must be a timezone-aware datetime after flush."""
        user = await make_user()
        mindmap = await make_map(owner=user)
        src = await make_node(mindmap=mindmap, label="X")
        tgt = await make_node(mindmap=mindmap, label="Y")
        edge = await make_edge(mindmap=mindmap, source=src, target=tgt)
        assert isinstance(edge.created_at, datetime)
        assert edge.created_at.tzinfo is not None


# ── Pydantic schema validation ────────────────────────────────────────────────
# These are pure unit tests — no database required.


class TestSchemaValidation:
    """Tests for Pydantic schema validation rules defined in schemas/graph.py."""

    def test_node_create_rejects_invalid_hex_color(self) -> None:
        """``NodeCreate`` must reject colours that are not 6-digit hex strings."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="color"):
            NodeCreate(label="Node", color="red")  # not a #RRGGBB value

    def test_node_create_rejects_empty_label(self) -> None:
        """``NodeCreate`` must reject an empty string for ``label``."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="label"):
            NodeCreate(label="")

    def test_node_create_accepts_valid_color(self) -> None:
        """``NodeCreate`` must accept a valid #RRGGBB color."""
        node = NodeCreate(label="Node", color="#aAbBcC")
        assert node.color == "#aAbBcC"

    def test_node_update_is_fully_optional(self) -> None:
        """``NodeUpdate`` must be valid with no fields supplied."""
        update = NodeUpdate()
        assert update.label is None
        assert update.x is None
        assert update.color is None

    def test_edge_create_self_loop_detected(self) -> None:
        """``EdgeCreate.validate_no_self_loop()`` must raise for equal IDs."""
        same_id = uuid.uuid4()
        edge = EdgeCreate(source_id=same_id, target_id=same_id)
        with pytest.raises(ValueError, match="different nodes"):
            edge.validate_no_self_loop()

    def test_edge_create_different_nodes_passes(self) -> None:
        """``EdgeCreate.validate_no_self_loop()`` must not raise for different IDs."""
        edge = EdgeCreate(source_id=uuid.uuid4(), target_id=uuid.uuid4())
        edge.validate_no_self_loop()  # must not raise

    def test_user_create_rejects_short_password(self) -> None:
        """``UserCreate`` must reject passwords shorter than 8 characters."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="password"):
            UserCreate(email="x@example.com", display_name="X", password="short")

    def test_user_create_rejects_invalid_email(self) -> None:
        """``UserCreate`` must reject a malformed email address."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="email"):
            UserCreate(email="not-an-email", display_name="X", password="password123")
