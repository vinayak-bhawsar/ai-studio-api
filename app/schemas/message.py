from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent import AgentDecision


class MessageCreateRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=100000,
    )


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class ChatResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    agent_decision: AgentDecision