from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.scene import Scene


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    scene_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "scenes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    shot_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    action: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    camera_framing: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    camera_movement: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    camera_angle: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    composition: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    cast_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    start_frame_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    end_frame_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    generation_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    video_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    video_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    production_settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    asset_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    scene: Mapped[Scene] = relationship(
        "Scene",
        back_populates="shots",
        foreign_keys=[scene_id],
    )

    project: Mapped[Project] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="select",
    )

    __table_args__ = (
        UniqueConstraint(
            "scene_id",
            "shot_number",
            name="uq_shot_scene_number",
        ),
    )
