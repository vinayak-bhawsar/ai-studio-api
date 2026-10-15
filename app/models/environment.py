import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Environment(Base):
    __tablename__ = "environments"

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

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    environment_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    time_of_day: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    visual_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    architecture: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    lighting: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    materials: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    atmosphere: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    reference_images: Mapped[list] = mapped_column(
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

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "name",
            name="uq_environment_project_name",
        ),
    )