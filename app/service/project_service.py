from math import ceil
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repository.project_repo import (
    create_project,
    delete_project,
    get_project_by_id,
    get_projects_by_user,
    update_project,
)
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)


def create_user_project(
    db: Session,
    *,
    user_id: UUID,
    data: ProjectCreateRequest,
) -> ProjectResponse:
    """
    Create a project for the authenticated user.

    A default Style Book is created automatically as part of
    project creation. This means every newly created project
    has a Style Book available immediately.
    """

    title = data.title.strip()

    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Project title cannot be empty.",
        )

    # Idempotency / Deduplication:
    # If the user created a project with the same title within the last 5 seconds,
    # return that project rather than creating a duplicate row.
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models.project import Project

    recent_cutoff = datetime.utcnow() - timedelta(seconds=5)
    existing_recent = db.scalar(
        select(Project)
        .where(
            Project.user_id == user_id,
            Project.created_at >= recent_cutoff,
        )
        .order_by(Project.created_at.desc())
    )

    if existing_recent:
        return ProjectResponse(
            id=str(existing_recent.id),
            title=existing_recent.title,
            created_at=existing_recent.created_at,
            updated_at=existing_recent.updated_at,
        )

    project = create_project(
        db,
        user_id=user_id,
        title=title,
    )

    return ProjectResponse(
        id=str(project.id),
        title=project.title,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def get_user_projects(
    db: Session,
    *,
    user_id: UUID,
    page: int,
    limit: int,
) -> ProjectListResponse:
    """Return paginated projects for the authenticated user."""

    offset = (page - 1) * limit

    projects, total = get_projects_by_user(
        db,
        user_id=user_id,
        offset=offset,
        limit=limit,
    )

    total_pages = ceil(total / limit) if total else 0

    items = [
        ProjectResponse(
            id=str(project.id),
            title=project.title,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        for project in projects
    ]

    return ProjectListResponse(
        items=items,
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
    )


def get_user_project(
    db: Session,
    *,
    project_id: UUID,
    user_id: UUID,
) -> ProjectResponse:
    """Return a project owned by the authenticated user."""

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

    return ProjectResponse(
        id=str(project.id),
        title=project.title,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def update_user_project(
    db: Session,
    *,
    project_id: UUID,
    user_id: UUID,
    data: ProjectUpdateRequest,
) -> ProjectResponse:
    """Update a project owned by the authenticated user."""

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
            detail="Project title cannot be empty.",
        )

    project = update_project(
        db,
        project=project,
        title=title,
    )

    return ProjectResponse(
        id=str(project.id),
        title=project.title,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def delete_user_project(
    db: Session,
    *,
    project_id: UUID,
    user_id: UUID,
) -> None:
    """Delete a project owned by the authenticated user."""

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

    delete_project(
        db,
        project=project,
    )
