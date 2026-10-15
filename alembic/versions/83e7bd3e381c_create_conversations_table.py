"""create conversations table

Revision ID: 83e7bd3e381c
Revises: d8dc3bfff6ae
Create Date: 2026-10-05 14:48:20.927354
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "83e7bd3e381c"

down_revision: Union[str, Sequence[str], None] = "d8dc3bfff6ae"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversations table."""

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_conversations_project_id",
        "conversations",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop conversations table."""

    op.drop_index(
        "ix_conversations_project_id",
        table_name="conversations",
    )

    op.drop_table("conversations")