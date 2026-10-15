import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.environment import Environment
from app.models.screenplay import Screenplay, ScreenplayVersion


def get_environment_by_id(
    db: Session,
    environment_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Environment | None:
    statement = select(Environment).where(
        Environment.id == environment_id,
        Environment.project_id == project_id,
    )

    return db.scalar(statement)


def get_environment_by_name(
    db: Session,
    project_id: uuid.UUID,
    name: str,
) -> Environment | None:
    statement = select(Environment).where(
        Environment.project_id == project_id,
        Environment.name == name,
    )

    return db.scalar(statement)


def list_environments(
    db: Session,
    project_id: uuid.UUID,
) -> list[Environment]:
    statement = (
        select(Environment)
        .where(
            Environment.project_id == project_id,
        )
        .order_by(Environment.created_at.asc())
    )

    return list(db.scalars(statement).all())


def create_environment(
    db: Session,
    project_id: uuid.UUID,
    source_screenplay_version_id: uuid.UUID | None,
    content: dict,
) -> Environment:
    environment = Environment(
        project_id=project_id,
        source_screenplay_version_id=source_screenplay_version_id,
        name=content["name"],
        description=content["description"],
        environment_type=content["environment_type"],
        time_of_day=content["time_of_day"],
        visual_description=content["visual_description"],
        architecture=content["architecture"],
        lighting=content["lighting"],
        materials=content["materials"],
        atmosphere=content["atmosphere"],
        reference_images=[],
    )

    db.add(environment)
    db.flush()

    return environment


def update_environment(
    db: Session,
    environment: Environment,
    content: dict,
) -> Environment:
    environment.name = content["name"]
    environment.description = content["description"]
    environment.environment_type = content["environment_type"]
    environment.time_of_day = content["time_of_day"]
    environment.visual_description = content["visual_description"]
    environment.architecture = content["architecture"]
    environment.lighting = content["lighting"]
    environment.materials = content["materials"]
    environment.atmosphere = content["atmosphere"]

    db.flush()

    return environment


def delete_environment(
    db: Session,
    environment: Environment,
) -> None:
    db.delete(environment)
    db.flush()


def get_latest_screenplay_version_by_project(
    db: Session,
    project_id: uuid.UUID,
) -> ScreenplayVersion | None:
    statement = (
        select(ScreenplayVersion)
        .join(
            Screenplay,
            Screenplay.id == ScreenplayVersion.screenplay_id,
        )
        .join(
            Conversation,
            Conversation.id == Screenplay.conversation_id,
        )
        .where(
            Conversation.project_id == project_id,
        )
        .order_by(
            ScreenplayVersion.created_at.desc(),
        )
        .limit(1)
    )

    return db.scalar(statement)