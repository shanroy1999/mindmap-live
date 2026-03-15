"""add node_type to nodes

Revision ID: a8f3b2c1d4e5
Revises:     f62da81744b3
Create Date: 2026-03-15 00:00:00.000000+00:00
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a8f3b2c1d4e5'
down_revision: Optional[str] = 'f62da81744b3'
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        'nodes',
        sa.Column(
            'node_type',
            sa.String(length=20),
            server_default=sa.text("'idea'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('nodes', 'node_type')
