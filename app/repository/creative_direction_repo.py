from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.creative_direction import CreativeDirection


def create_creative_direction(
    db: Session,
    *,
    conversation_id: UUID,
    title: str,
    description: str,
) -> CreativeDirection:
    direction = CreativeDirection(
        conversation_id=conversation_id,
        title=title,
        description=description,
    )

    db.add(direction)
    db.commit()
    db.refresh(direction)

    return direction


def create_creative_directions(
    db: Session,
    *,
    conversation_id: UUID,
    directions: list[dict],
) -> list[CreativeDirection]:
    records = [
        CreativeDirection(
            conversation_id=conversation_id,
            title=direction["title"],
            description=direction["description"],
        )
        for direction in directions
    ]

    db.add_all(records)
    db.commit()

    for record in records:
        db.refresh(record)

    return records


def get_creative_direction_by_id(
    db: Session,
    *,
    direction_id: UUID,
    conversation_id: UUID,
) -> CreativeDirection | None:
    statement = select(CreativeDirection).where(
        CreativeDirection.id == direction_id,
        CreativeDirection.conversation_id == conversation_id,
    )

    return db.scalar(statement)


def get_creative_directions_by_ids(
    db: Session,
    *,
    conversation_id: UUID,
    direction_ids: list[UUID],
) -> list[CreativeDirection]:
    """
    Get specific creative directions by their IDs.

    The order of the returned records follows direction_ids.
    """

    if not direction_ids:
        return []

    statement = select(CreativeDirection).where(
        CreativeDirection.conversation_id == conversation_id,
        CreativeDirection.id.in_(direction_ids),
    )

    records = list(db.scalars(statement).all())

    records_by_id = {
        record.id: record
        for record in records
    }

    return [
        records_by_id[direction_id]
        for direction_id in direction_ids
        if direction_id in records_by_id
    ]


def get_creative_directions_by_conversation(
    db: Session,
    *,
    conversation_id: UUID,
) -> list[CreativeDirection]:
    statement = (
        select(CreativeDirection)
        .where(
            CreativeDirection.conversation_id == conversation_id
        )
        .order_by(CreativeDirection.created_at.asc())
    )

    return list(db.scalars(statement).all())