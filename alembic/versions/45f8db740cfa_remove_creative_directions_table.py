"""remove creative directions table

Revision ID: 45f8db740cfa
Revises: c8c07b7129ef
Create Date: 2026-10-06 11:33:21.949772
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "45f8db740cfa"
down_revision: Union[str, Sequence[str], None] = "c8c07b7129ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_conversations_selected_direction_id",
        "conversations",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_creative_directions_conversation_id",
        table_name="creative_directions",
    )

    op.drop_table("creative_directions")


def downgrade() -> None:
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

    op.create_foreign_key(
        "fk_conversations_selected_direction_id",
        "conversations",
        "creative_directions",
        ["selected_direction_id"],
        ["id"],
        ondelete="SET NULL",
    )