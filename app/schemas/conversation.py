from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.message import MessageResponse


class ConversationCreateRequest(BaseModel):
    title: str = Field(
        default="New Chat",
        min_length=1,
        max_length=200,
    )


class ConversationUpdateRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
    )


class ConversationResponse(BaseModel):
    id: str
    project_id: str
    title: str
    stage: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []


class ConversationListItem(BaseModel):
    id: str
    project_id: str
    title: str
    stage: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    page: int
    limit: int
    total: int
    total_pages: int