"""add creative directions

Revision ID: 09e115aee84b
Revises: a1b2c3d4e5f6
Create Date: 2026-10-05 17:45:11.711420
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "09e115aee84b"

down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # Create creative_directions table
    # ---------------------------------------------------------

    op.create_table(
        "creative_directions",

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
            "title",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "description",
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
        "ix_creative_directions_conversation_id",
        "creative_directions",
        ["conversation_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # Add selected direction to conversations
    # ---------------------------------------------------------

    op.add_column(
        "conversations",
        sa.Column(
            "selected_direction_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_conversations_selected_direction_id",
        "conversations",
        "creative_directions",
        ["selected_direction_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Remove foreign key first
    op.drop_constraint(
        "fk_conversations_selected_direction_id",
        "conversations",
        type_="foreignkey",
    )

    # Remove selected direction column
    op.drop_column(
        "conversations",
        "selected_direction_id",
    )

    # Remove creative directions index
    op.drop_index(
        "ix_creative_directions_conversation_id",
        table_name="creative_directions",
    )

    # Remove creative directions table
    op.drop_table(
        "creative_directions",
    )