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
    from app.models.environment import Environment
    from app.models.project import Project
    from app.models.screenplay import ScreenplayVersion
    from app.models.shot import Shot


class Scene(Base):
    __tablename__ = "scenes"

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

    source_screenplay_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "screenplay_versions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    scene_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    heading: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    time_of_day: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    narrative_purpose: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "environments.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    cast_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
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
    shots: Mapped[list[Shot]] = relationship(
        "Shot",
        back_populates="scene",
        cascade="all, delete-orphan",
        order_by="Shot.shot_number",
    )

    environment: Mapped[Environment | None] = relationship(
        "Environment",
        foreign_keys=[environment_id],
        lazy="select",
    )

    project: Mapped[Project] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="select",
    )

    screenplay_version: Mapped[ScreenplayVersion | None] = relationship(
        "ScreenplayVersion",
        foreign_keys=[source_screenplay_version_id],
        lazy="select",
    )

    @property
    def source_screenplay_version(self) -> ScreenplayVersion | None:
        return self.screenplay_version


    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "scene_number",
            name="uq_scene_project_number",
        ),
    )
