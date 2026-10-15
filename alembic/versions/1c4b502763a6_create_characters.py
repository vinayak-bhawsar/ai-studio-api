"""create characters

Revision ID: 1c4b502763a6
Revises: 7b1c2d3e4f5a
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "1c4b502763a6"
down_revision: Union[str, Sequence[str], None] = "7b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "characters",
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
            "source_screenplay_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "age",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "appearance",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "personality",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "wardrobe",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "visual_style",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "reference_images",
            postgresql.JSONB(astext_type=sa.Text()),
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
        sa.ForeignKeyConstraint(
            ["source_screenplay_version_id"],
            ["screenplay_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_character_project_name",
        ),
    )

    op.create_index(
        "ix_characters_project_id",
        "characters",
        ["project_id"],
        unique=False,
    )

    op.create_index(
        "ix_characters_source_screenplay_version_id",
        "characters",
        ["source_screenplay_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_characters_source_screenplay_version_id",
        table_name="characters",
    )

    op.drop_index(
        "ix_characters_project_id",
        table_name="characters",
    )

    op.drop_table("characters")