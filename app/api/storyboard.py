from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.storyboard import (
    FrameGenerateResponse,
    SceneCreateRequest,
    SceneResponse,
    SceneUpdateRequest,
    ShotCreateRequest,
    ShotFrameGenerateRequest,
    ShotResponse,
    ShotUpdateRequest,
    StoryboardFramesGenerateRequest,
    StoryboardFramesGenerateResponse,
    StoryboardGenerateRequest,
    StoryboardResponse,
)
from app.service.storyboard_service import (
    create_scene_entry,
    create_shot_entry,
    delete_scene_entry,
    delete_shot_entry,
    generate_shot_frame,
    generate_storyboard,
    generate_storyboard_frames,
    get_scene_details,
    get_scene_shots,
    get_shot_details,
    get_storyboard,
    update_scene_entry,
    update_shot_entry,
)


router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["Storyboard"],
)


def _handle_service_error(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        ) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Storyboard operation failed: {exc}",
    ) from exc


# =========================================================================
# STORYBOARD ROOT ENDPOINTS
# =========================================================================

@router.get(
    "/storyboard",
    response_model=StoryboardResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_storyboard(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve a project's storyboard scenes and ordered shots."""
    try:
        return get_storyboard(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/storyboard/generate",
    response_model=StoryboardResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_project_storyboard(
    project_id: UUID,
    payload: StoryboardGenerateRequest = StoryboardGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate storyboard scenes and shot breakdown from the saved screenplay."""
    try:
        return await generate_storyboard(
            db=db,
            project_id=project_id,
            user_id=user.id,
            instructions=payload.instructions,
            force_regenerate=payload.force_regenerate,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/storyboard/generate-frames",
    response_model=StoryboardFramesGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_project_storyboard_frames(
    project_id: UUID,
    payload: StoryboardFramesGenerateRequest = StoryboardFramesGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Batch generate reference start or end frames for shots in the storyboard."""
    try:
        return await generate_storyboard_frames(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


# =========================================================================
# SCENE ENDPOINTS
# =========================================================================

@router.get(
    "/scenes",
    response_model=list[SceneResponse],
    status_code=status.HTTP_200_OK,
)
def list_project_scenes(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all scenes in the project."""
    try:
        sb = get_storyboard(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )
        return sb.get("scenes", [])
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/scenes",
    response_model=SceneResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_scene(
    project_id: UUID,
    payload: SceneCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new scene in the project."""
    try:
        return create_scene_entry(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.get(
    "/scenes/{scene_id}",
    response_model=SceneResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_scene(
    project_id: UUID,
    scene_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve a specific scene and its ordered shots."""
    try:
        return get_scene_details(
            db=db,
            project_id=project_id,
            scene_id=scene_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.put(
    "/scenes/{scene_id}",
    response_model=SceneResponse,
    status_code=status.HTTP_200_OK,
)
def update_project_scene(
    project_id: UUID,
    scene_id: UUID,
    payload: SceneUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update scene details."""
    try:
        return update_scene_entry(
            db=db,
            project_id=project_id,
            scene_id=scene_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.delete(
    "/scenes/{scene_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_scene(
    project_id: UUID,
    scene_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a scene and its associated shots, maintaining ordering."""
    try:
        delete_scene_entry(
            db=db,
            project_id=project_id,
            scene_id=scene_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


# =========================================================================
# SHOT ENDPOINTS
# =========================================================================

@router.get(
    "/scenes/{scene_id}/shots",
    response_model=list[ShotResponse],
    status_code=status.HTTP_200_OK,
)
def list_scene_shots(
    project_id: UUID,
    scene_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve ordered shots for a scene."""
    try:
        return get_scene_shots(
            db=db,
            project_id=project_id,
            scene_id=scene_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/scenes/{scene_id}/shots",
    response_model=ShotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scene_shot(
    project_id: UUID,
    scene_id: UUID,
    payload: ShotCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a shot in a scene."""
    try:
        return create_shot_entry(
            db=db,
            project_id=project_id,
            scene_id=scene_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.get(
    "/shots/{shot_id}",
    response_model=ShotResponse,
    status_code=status.HTTP_200_OK,
)
def get_shot(
    project_id: UUID,
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve a specific shot."""
    try:
        return get_shot_details(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.put(
    "/shots/{shot_id}",
    response_model=ShotResponse,
    status_code=status.HTTP_200_OK,
)
def update_shot(
    project_id: UUID,
    shot_id: UUID,
    payload: ShotUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update shot details."""
    try:
        return update_shot_entry(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.delete(
    "/shots/{shot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shot(
    project_id: UUID,
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a shot, maintaining shot ordering in the scene."""
    try:
        delete_shot_entry(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/shots/{shot_id}/generate-frame",
    response_model=FrameGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_shot_reference_frame(
    project_id: UUID,
    shot_id: UUID,
    payload: ShotFrameGenerateRequest = ShotFrameGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate or retrieve a start or end reference frame for a shot."""
    try:
        return await generate_shot_frame(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)
