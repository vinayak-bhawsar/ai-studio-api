from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
)
from app.schemas.response import APIResponse
from app.service.conversation_service import (
    create_project_conversation,
    delete_project_conversation,
    get_project_conversation,
    get_project_conversations,
    update_project_conversation,
)


router = APIRouter(
    prefix="/projects/{project_id}/conversations",
    tags=["Conversations"],
)


@router.post(
    "",
    response_model=APIResponse[ConversationResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    project_id: UUID,
    data: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse[ConversationResponse]:

    conversation = create_project_conversation(
        db,
        project_id=project_id,
        user_id=current_user.id,
        data=data,
    )

    return APIResponse(
        success=True,
        message="Conversation created successfully.",
        data=conversation,
    )


@router.get(
    "",
    response_model=APIResponse[ConversationListResponse],
)
def get_conversations(
    project_id: UUID,
    page: int = Query(
        default=1,
        ge=1,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse[ConversationListResponse]:

    conversations = get_project_conversations(
        db,
        project_id=project_id,
        user_id=current_user.id,
        page=page,
        limit=limit,
    )

    return APIResponse(
        success=True,
        message="Conversations fetched successfully.",
        data=conversations,
    )


@router.get(
    "/{conversation_id}",
    response_model=APIResponse[ConversationResponse],
)
def get_conversation(
    project_id: UUID,
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse[ConversationResponse]:

    conversation = get_project_conversation(
        db,
        project_id=project_id,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    return APIResponse(
        success=True,
        message="Conversation fetched successfully.",
        data=conversation,
    )


@router.delete(
    "/{conversation_id}",
    response_model=APIResponse[None],
)
def delete_conversation(
    project_id: UUID,
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse[None]:

    delete_project_conversation(
        db,
        project_id=project_id,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    return APIResponse(
        success=True,
        message="Conversation deleted successfully.",
        data=None,
    )


@router.patch(
    "/{conversation_id}",
    response_model=APIResponse[ConversationResponse],
)
def update_conversation(
    project_id: UUID,
    conversation_id: UUID,
    data: ConversationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIResponse[ConversationResponse]:

    conversation = update_project_conversation(
        db,
        project_id=project_id,
        conversation_id=conversation_id,
        user_id=current_user.id,
        data=data,
    )

    return APIResponse(
        success=True,
        message="Conversation updated successfully.",
        data=conversation,
    )