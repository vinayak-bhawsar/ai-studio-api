from math import ceil
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repository.conversation_repo import (
    create_conversation,
    delete_conversation,
    get_conversation_by_id,
    get_conversations_by_project,
)
from app.repository.message_repo import (
    create_message,
    get_messages_by_conversation,
)
from app.repository.project_repo import (
    get_project_by_id,
)
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
)
from app.schemas.message import MessageResponse

DEFAULT_WELCOME_MESSAGE = (
    "Welcome to our AI video studio! I'm excited to collaborate with you "
    "on your video project. Can you please share a bit about your idea "
    "or story premise to get us started?"
)


def create_project_conversation(
    db: Session,
    *,
    project_id: UUID,
    user_id: UUID,
    data: ConversationCreateRequest,
) -> ConversationResponse:
    """Create a conversation inside a user's project."""

    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    title = data.title.strip()

    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conversation title cannot be empty.",
        )

    conversation = create_conversation(
        db,
        project_id=project_id,
        title=title,
    )

    welcome_message = create_message(
        db,
        conversation_id=conversation.id,
        role="assistant",
        content=DEFAULT_WELCOME_MESSAGE,
        metadata={"action": "ask_question"},
    )

    return ConversationResponse(
        id=str(conversation.id),
        project_id=str(conversation.project_id),
        title=conversation.title,
        stage=conversation.stage,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageResponse(
                id=str(welcome_message.id),
                conversation_id=str(welcome_message.conversation_id),
                role=welcome_message.role,
                content=welcome_message.content,
                created_at=welcome_message.created_at,
                updated_at=welcome_message.updated_at,
            )
        ],
    )


def get_project_conversations(
    db: Session,
    *,
    project_id: UUID,
    user_id: UUID,
    page: int,
    limit: int,
) -> ConversationListResponse:
    """Return paginated conversations for a project."""

    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    offset = (page - 1) * limit

    conversations, total = get_conversations_by_project(
        db,
        project_id=project_id,
        offset=offset,
        limit=limit,
    )

    # If an existing project has no conversations yet, create the default conversation and welcome message immediately
    if total == 0 and offset == 0:
        default_conv = create_conversation(
            db,
            project_id=project_id,
            title="Creative Idea",
        )
        create_message(
            db,
            conversation_id=default_conv.id,
            role="assistant",
            content=DEFAULT_WELCOME_MESSAGE,
            metadata={"action": "ask_question"},
        )
        conversations = [default_conv]
        total = 1

    total_pages = ceil(total / limit) if total else 0

    items = [
        ConversationListItem(
            id=str(conversation.id),
            project_id=str(conversation.project_id),
            title=conversation.title,
            stage=conversation.stage,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation in conversations
    ]

    return ConversationListResponse(
        items=items,
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
    )


def get_project_conversation(
    db: Session,
    *,
    project_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
) -> ConversationResponse:
    """Return a conversation with its complete message history."""

    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    conversation = get_conversation_by_id(
        db,
        conversation_id=conversation_id,
        project_id=project_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    messages = get_messages_by_conversation(
        db,
        conversation_id=conversation_id,
    )

    if not messages:
        welcome_message = create_message(
            db,
            conversation_id=conversation.id,
            role="assistant",
            content=DEFAULT_WELCOME_MESSAGE,
            metadata={"action": "ask_question"},
        )
        messages = [welcome_message]

    message_items = [
        MessageResponse(
            id=str(message.id),
            conversation_id=str(message.conversation_id),
            role=message.role,
            content=message.content,
            metadata=message.message_metadata,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )
        for message in messages
    ]

    return ConversationResponse(
        id=str(conversation.id),
        project_id=str(conversation.project_id),
        title=conversation.title,
        stage=conversation.stage,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=message_items,
    )


def delete_project_conversation(
    db: Session,
    *,
    project_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
) -> None:
    """Delete a conversation belonging to the authenticated user."""

    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    conversation = get_conversation_by_id(
        db,
        conversation_id=conversation_id,
        project_id=project_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    delete_conversation(
        db,
        conversation=conversation,
    )


def update_project_conversation(
    db: Session,
    *,
    project_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    data: ConversationUpdateRequest,
) -> ConversationResponse:
    """Update conversation title."""

    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    conversation = get_conversation_by_id(
        db,
        conversation_id=conversation_id,
        project_id=project_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    title = data.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conversation title cannot be empty.",
        )

    conversation.title = title
    db.commit()
    db.refresh(conversation)

    messages = get_messages_by_conversation(
        db,
        conversation_id=conversation_id,
    )

    message_items = [
        MessageResponse(
            id=str(message.id),
            conversation_id=str(message.conversation_id),
            role=message.role,
            content=message.content,
            metadata=message.message_metadata,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )
        for message in messages
    ]

    return ConversationResponse(
        id=str(conversation.id),
        project_id=str(conversation.project_id),
        title=conversation.title,
        stage=conversation.stage,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=message_items,
    )