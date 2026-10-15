from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


def create_message(
    db: Session,
    *,
    conversation_id: UUID,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        message_metadata=metadata,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def get_messages_by_conversation(
    db: Session,
    *,
    conversation_id: UUID,
) -> list[Message]:
    statement = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id
        )
        .order_by(
            Message.created_at.asc()
        )
    )

    return list(
        db.scalars(statement).all()
    )