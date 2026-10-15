"""create environments

revision = "bcb477455de4"
down_revision = "1c4b502763a6"
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "bcb477455de4"
down_revision: Union[str, Sequence[str], None] = "1c4b502763a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "environments",
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
            "environment_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "time_of_day",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "visual_description",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "architecture",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "lighting",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "materials",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "atmosphere",
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
            name="uq_environment_project_name",
        ),
    )

    op.create_index(
        "ix_environments_project_id",
        "environments",
        ["project_id"],
        unique=False,
    )

    op.create_index(
        "ix_environments_source_screenplay_version_id",
        "environments",
        ["source_screenplay_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_environments_source_screenplay_version_id",
        table_name="environments",
    )

    op.drop_index(
        "ix_environments_project_id",
        table_name="environments",
    )

    op.drop_table("environments")