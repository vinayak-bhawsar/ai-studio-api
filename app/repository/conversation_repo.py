from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation


def create_conversation(
    db: Session,
    *,
    project_id: UUID,
    title: str,
) -> Conversation:
    """Create and persist a conversation."""

    conversation = Conversation(
        project_id=project_id,
        title=title,
        stage="idea",
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


def get_conversations_by_project(
    db: Session,
    *,
    project_id: UUID,
    offset: int,
    limit: int,
) -> tuple[list[Conversation], int]:
    """Return paginated conversations for a project."""

    total = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.project_id == project_id
        )
    ) or 0

    statement = (
        select(Conversation)
        .where(
            Conversation.project_id == project_id
        )
        .order_by(
            Conversation.created_at.desc()
        )
        .offset(offset)
        .limit(limit)
    )

    conversations = list(
        db.scalars(statement).all()
    )

    return conversations, total


def get_conversation_by_id(
    db: Session,
    *,
    conversation_id: UUID,
    project_id: UUID,
) -> Conversation | None:
    """Return a conversation belonging to a project."""

    statement = (
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.project_id == project_id,
        )
    )

    return db.scalar(statement)


def delete_conversation(
    db: Session,
    *,
    conversation: Conversation,
) -> None:
    """Delete a conversation."""

    db.delete(conversation)
    db.commit()