import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.conversation import Conversation
from app.models.screenplay import Screenplay, ScreenplayVersion


def get_character_by_id(
    db: Session,
    character_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Character | None:
    statement = select(Character).where(
        Character.id == character_id,
        Character.project_id == project_id,
    )

    return db.scalar(statement)


def get_character_by_name(
    db: Session,
    project_id: uuid.UUID,
    name: str,
) -> Character | None:
    statement = select(Character).where(
        Character.project_id == project_id,
        Character.name == name,
    )

    return db.scalar(statement)


def list_characters(
    db: Session,
    project_id: uuid.UUID,
) -> list[Character]:
    statement = (
        select(Character)
        .where(
            Character.project_id == project_id,
        )
        .order_by(Character.created_at.asc())
    )

    return list(db.scalars(statement).all())


def create_character(
    db: Session,
    project_id: uuid.UUID,
    source_screenplay_version_id: uuid.UUID | None,
    content: dict,
) -> Character:
    character = Character(
        project_id=project_id,
        source_screenplay_version_id=source_screenplay_version_id,
        name=content["name"],
        description=content["description"],
        role=content["role"],
        age=content["age"],
        appearance=content["appearance"],
        personality=content["personality"],
        wardrobe=content["wardrobe"],
        visual_style=content["visual_style"],
        reference_images=[],
    )

    db.add(character)
    db.flush()

    return character


def update_character(
    db: Session,
    character: Character,
    content: dict,
) -> Character:
    character.name = content["name"]
    character.description = content["description"]
    character.role = content["role"]
    character.age = content["age"]
    character.appearance = content["appearance"]
    character.personality = content["personality"]
    character.wardrobe = content["wardrobe"]
    character.visual_style = content["visual_style"]

    db.flush()

    return character


def delete_character(
    db: Session,
    character: Character,
) -> None:
    db.delete(character)
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