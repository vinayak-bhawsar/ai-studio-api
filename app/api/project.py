from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.schemas.response import APIResponse
from app.service.project_service import (
    create_user_project,
    delete_user_project,
    get_user_project,
    get_user_projects,
    update_user_project,
)


router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.post(
    "",
    response_model=APIResponse[ProjectResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreateRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
) -> APIResponse[ProjectResponse]:
    """Create a project for the authenticated user."""

    project = create_user_project(
        db,
        user_id=current_user.id,
        data=data,
    )

    return APIResponse(
        success=True,
        message="Project created successfully.",
        data=project,
    )


@router.get(
    "",
    response_model=APIResponse[ProjectListResponse],
)
def get_projects(
    page: int = Query(
        default=1,
        ge=1,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
) -> APIResponse[ProjectListResponse]:
    """Return paginated projects for the authenticated user."""

    projects = get_user_projects(
        db,
        user_id=current_user.id,
        page=page,
        limit=limit,
    )

    return APIResponse(
        success=True,
        message="Projects fetched successfully.",
        data=projects,
    )


@router.get(
    "/{project_id}",
    response_model=APIResponse[ProjectResponse],
)
def get_project(
    project_id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
) -> APIResponse[ProjectResponse]:
    """Return a project owned by the authenticated user."""

    project = get_user_project(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )

    return APIResponse(
        success=True,
        message="Project fetched successfully.",
        data=project,
    )


@router.put(
    "/{project_id}",
    response_model=APIResponse[ProjectResponse],
)
def update_project(
    project_id: UUID,
    data: ProjectUpdateRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
) -> APIResponse[ProjectResponse]:
    """Update a project owned by the authenticated user."""

    project = update_user_project(
        db,
        project_id=project_id,
        user_id=current_user.id,
        data=data,
    )

    return APIResponse(
        success=True,
        message="Project updated successfully.",
        data=project,
    )


@router.delete(
    "/{project_id}",
    response_model=APIResponse[None],
)
def delete_project(
    project_id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
) -> APIResponse[None]:
    """Delete a project owned by the authenticated user."""

    delete_user_project(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )

    return APIResponse(
        success=True,
        message="Project deleted successfully.",
        data=None,
    )