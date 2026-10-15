"""create projects table

Revision ID: d8dc3bfff6ae
Revises: d28ff2a3e5ad
Create Date: 2026-10-05 13:03:04.623743
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8dc3bfff6ae"
down_revision: Union[str, Sequence[str], None] = "d28ff2a3e5ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create projects table."""

    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
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
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_projects_user_id",
        "projects",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop projects table."""

    op.drop_index(
        "ix_projects_user_id",
        table_name="projects",
    )

    op.drop_table("projects")