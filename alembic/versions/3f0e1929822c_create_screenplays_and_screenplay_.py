"""create screenplays and screenplay versions

Revision ID: 3f0e1929822c
Revises: 45f8db740cfa
Create Date: 2026-10-06 12:15:54.726857
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3f0e1929822c"
down_revision: Union[str, Sequence[str], None] = "45f8db740cfa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screenplays",
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
        sa.UniqueConstraint("conversation_id"),
    )

    op.create_index(
        "ix_screenplays_conversation_id",
        "screenplays",
        ["conversation_id"],
        unique=False,
    )

    op.create_table(
        "screenplay_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "screenplay_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "logline",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "content",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "is_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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
            ["screenplay_id"],
            ["screenplays.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "screenplay_id",
            "version",
            name="uq_screenplay_version",
        ),
    )

    op.create_index(
        "ix_screenplay_versions_screenplay_id",
        "screenplay_versions",
        ["screenplay_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_screenplay_versions_screenplay_id",
        table_name="screenplay_versions",
    )

    op.drop_table("screenplay_versions")

    op.drop_index(
        "ix_screenplays_conversation_id",
        table_name="screenplays",
    )

    op.drop_table("screenplays")