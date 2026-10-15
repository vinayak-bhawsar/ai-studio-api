import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.screenplay import Screenplay, ScreenplayVersion


def get_screenplay_by_conversation(
    db: Session,
    conversation_id: uuid.UUID,
) -> Screenplay | None:
    statement = select(Screenplay).where(
        Screenplay.conversation_id == conversation_id
    )

    return db.scalar(statement)


def create_screenplay(
    db: Session,
    conversation_id: uuid.UUID,
) -> Screenplay:
    screenplay = Screenplay(
        conversation_id=conversation_id,
    )

    db.add(screenplay)
    db.flush()

    return screenplay


def get_screenplay_version(
    db: Session,
    screenplay_id: uuid.UUID,
    version: int,
) -> ScreenplayVersion | None:
    statement = select(ScreenplayVersion).where(
        ScreenplayVersion.screenplay_id == screenplay_id,
        ScreenplayVersion.version == version,
    )

    return db.scalar(statement)


def get_latest_screenplay_version(
    db: Session,
    screenplay_id: uuid.UUID,
) -> ScreenplayVersion | None:
    statement = (
        select(ScreenplayVersion)
        .where(
            ScreenplayVersion.screenplay_id == screenplay_id,
        )
        .order_by(ScreenplayVersion.version.desc())
        .limit(1)
    )

    return db.scalar(statement)


def create_screenplay_version(
    db: Session,
    screenplay_id: uuid.UUID,
    version: int,
    title: str,
    logline: str,
    content: dict,
) -> ScreenplayVersion:
    screenplay_version = ScreenplayVersion(
        screenplay_id=screenplay_id,
        version=version,
        title=title,
        logline=logline,
        content=content,
        is_locked=False,
    )

    db.add(screenplay_version)
    db.flush()

    return screenplay_version


def update_screenplay_version(
    db: Session,
    screenplay_version: ScreenplayVersion,
    title: str,
    logline: str,
    content: dict,
) -> ScreenplayVersion:
    screenplay_version.title = title
    screenplay_version.logline = logline
    screenplay_version.content = content

    db.flush()

    return screenplay_version


def list_screenplay_versions(
    db: Session,
    screenplay_id: uuid.UUID,
) -> list[ScreenplayVersion]:
    statement = (
        select(ScreenplayVersion)
        .where(
            ScreenplayVersion.screenplay_id == screenplay_id,
        )
        .order_by(ScreenplayVersion.version.asc())
    )

    return list(db.scalars(statement).all())