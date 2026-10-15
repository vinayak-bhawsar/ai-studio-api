"""create messages table

Revision ID: b86b93f7714d
Revises: 83e7bd3e381c
Create Date: 2026-10-05 15:08:55.017607
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b86b93f7714d"

down_revision: Union[str, Sequence[str], None] = "83e7bd3e381c"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create messages table."""

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
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
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_messages_conversation_id",
        "messages",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop messages table."""

    op.drop_index(
        "ix_messages_conversation_id",
        table_name="messages",
    )

    op.drop_table("messages")