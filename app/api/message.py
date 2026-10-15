from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.message import MessageCreateRequest
from app.service.message_service import (
    create_conversation_message_stream,
)


router = APIRouter(
    prefix=(
        "/projects/{project_id}"
        "/conversations/{conversation_id}"
        "/messages"
    ),
    tags=["Messages"],
)


@router.post(
    "",
    status_code=status.HTTP_200_OK,
)
async def create_message(
    project_id: UUID,
    conversation_id: UUID,
    data: MessageCreateRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return StreamingResponse(
        create_conversation_message_stream(
            db,
            project_id=project_id,
            conversation_id=conversation_id,
            user_id=current_user.id,
            data=data,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )