"""create style books

Revision ID: 7b1c2d3e4f5a
Revises: 3f0e1929822c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7b1c2d3e4f5a"
down_revision: Union[str, Sequence[str], None] = "3f0e1929822c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "style_books",
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
            "content",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )

    op.create_index(
        "ix_style_books_project_id",
        "style_books",
        ["project_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_style_books_project_id",
        table_name="style_books",
    )

    op.drop_table("style_books")