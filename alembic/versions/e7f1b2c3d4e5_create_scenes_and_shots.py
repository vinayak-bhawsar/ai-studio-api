"""create scenes and shots

Revision ID: e7f1b2c3d4e5
Revises: bcb477455de4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7f1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "bcb477455de4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenes",
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
            "scene_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "heading",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "time_of_day",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "narrative_purpose",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "cast_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
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
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "scene_number",
            name="uq_scene_project_number",
        ),
    )
    op.create_index(
        op.f("ix_scenes_project_id"),
        "scenes",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_scenes_source_screenplay_version_id"),
        "scenes",
        ["source_screenplay_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_scenes_environment_id"),
        "scenes",
        ["environment_id"],
        unique=False,
    )

    op.create_table(
        "shots",
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
            "scene_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "shot_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "camera_framing",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "camera_movement",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "camera_angle",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "composition",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "cast_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "start_frame_url",
            sa.String(length=1000),
            nullable=True,
        ),
        sa.Column(
            "end_frame_url",
            sa.String(length=1000),
            nullable=True,
        ),
        sa.Column(
            "generation_status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "video_url",
            sa.String(length=1000),
            nullable=True,
        ),
        sa.Column(
            "video_status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "production_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "asset_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scene_id",
            "shot_number",
            name="uq_shot_scene_number",
        ),
    )
    op.create_index(
        op.f("ix_shots_project_id"),
        "shots",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shots_scene_id"),
        "shots",
        ["scene_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_shots_scene_id"), table_name="shots")
    op.drop_index(op.f("ix_shots_project_id"), table_name="shots")
    op.drop_table("shots")

    op.drop_index(op.f("ix_scenes_environment_id"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_source_screenplay_version_id"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_project_id"), table_name="scenes")
    op.drop_table("scenes")
