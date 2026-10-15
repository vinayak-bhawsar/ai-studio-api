from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
    )


class ProjectUpdateRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
    )


class ProjectResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    page: int
    limit: int
    total: int
    total_pages: int