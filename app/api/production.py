from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.composition import (
    VideoComposeRequest,
    VideoComposeResponse,
)
from app.schemas.dialogue import (
    DialogueItem,
    DialogueVoiceGenerateRequest,
    DialogueVoiceGenerateResponse,
    ShotAudioMixRequest,
    ShotAudioMixResponse,
    ShotDialogueUpdateRequest,
)
from app.schemas.storyboard import (
    BatchVideoGenerateRequest,
    BatchVideoGenerateResponse,
    ProductionSettingsUpdateRequest,
    ProductionShotConfigResponse,
    ProductionStatusResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
)
from app.service.composition_service import (
    compose_project_video,
    get_project_composition_status,
)
from app.service.voice_service import (
    generate_shot_dialogue_voice,
    get_shot_dialogues,
    mix_dialogue_into_shot_video,
    populate_dialogues_from_screenplay,
    update_shot_dialogues,
)
from app.service.production_service import (
    generate_batch_videos,
    generate_shot_video,
    get_production_shot_config,
    get_production_studio_status,
    update_production_shot_config,
)


router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["Production Studio"],
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
        if "in progress" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        ) from exc
    if isinstance(exc, TimeoutError):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Production operation failed: {exc}",
    ) from exc


@router.get(
    "/shots/{shot_id}/production-config",
    response_model=ProductionShotConfigResponse,
    status_code=status.HTTP_200_OK,
)
def get_shot_production_config(
    project_id: UUID,
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve production configuration, prerequisites, and status for a shot."""
    try:
        return get_production_shot_config(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.put(
    "/shots/{shot_id}/production-config",
    response_model=ProductionShotConfigResponse,
    status_code=status.HTTP_200_OK,
)
def update_shot_production_config(
    project_id: UUID,
    shot_id: UUID,
    payload: ProductionSettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update production settings (duration, resolution, aspect ratio, motion) for a shot."""
    try:
        return update_production_shot_config(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/shots/{shot_id}/generate-video",
    response_model=VideoGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_single_shot_video(
    project_id: UUID,
    shot_id: UUID,
    payload: VideoGenerateRequest = VideoGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate production video asset for a shot using Google Veo model."""
    try:
        return await generate_shot_video(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.get(
    "/shots/{shot_id}/video-status",
    response_model=VideoGenerateResponse,
    status_code=status.HTTP_200_OK,
)
def get_shot_video_status(
    project_id: UUID,
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get video generation status and persisted URL for a shot."""
    try:
        cfg = get_production_shot_config(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
        return {
            "shot_id": str(shot_id),
            "video_url": cfg.get("video_url"),
            "status": cfg.get("video_status", "pending"),
            "duration_seconds": (cfg.get("production_settings") or {}).get("duration_seconds", 4),
            "message": f"Status: {cfg.get('video_status')}",
        }
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/production/generate-videos",
    response_model=BatchVideoGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_production_videos_batch(
    project_id: UUID,
    payload: BatchVideoGenerateRequest = BatchVideoGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Batch generate videos for all or selected shots in the storyboard."""
    try:
        return await generate_batch_videos(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.get(
    "/production/status",
    response_model=ProductionStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_production_status(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get project-wide production studio status and shot summaries."""
    try:
        return get_production_studio_status(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/compose-video",
    response_model=VideoComposeResponse,
    status_code=status.HTTP_200_OK,
)
def compose_full_video(
    project_id: UUID,
    payload: VideoComposeRequest = VideoComposeRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Combine generated clips in scene/shot chronological order into a full video."""
    try:
        return compose_project_video(
            db=db,
            project_id=project_id,
            user_id=user.id,
            allow_partial=payload.allow_partial,
            force_recompose=payload.force_recompose,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.get(
    "/compose-video/status",
    response_model=VideoComposeResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/composition",
    response_model=VideoComposeResponse,
    status_code=status.HTTP_200_OK,
)
def get_full_video_composition_status(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve the full video composition status, completed video URL, and shot sequence."""
    try:
        return get_project_composition_status(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.get(
    "/shots/{shot_id}/dialogues",
    response_model=list[DialogueItem],
    status_code=status.HTTP_200_OK,
)
def get_shot_dialogues_endpoint(
    project_id: UUID,
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve structured dialogue lines for a shot."""
    try:
        return get_shot_dialogues(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.put(
    "/shots/{shot_id}/dialogues",
    response_model=list[DialogueItem],
    status_code=status.HTTP_200_OK,
)
def update_shot_dialogues_endpoint(
    project_id: UUID,
    shot_id: UUID,
    payload: ShotDialogueUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update or save structured dialogue lines for a shot."""
    try:
        return update_shot_dialogues(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            dialogues=payload.dialogues,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/shots/{shot_id}/generate-voice",
    response_model=DialogueVoiceGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_shot_voice_endpoint(
    project_id: UUID,
    shot_id: UUID,
    payload: DialogueVoiceGenerateRequest = DialogueVoiceGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Synthesize speech audio for shot dialogues using Cloudflare Workers AI TTS."""
    try:
        return await generate_shot_dialogue_voice(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            dialogue_id=payload.dialogue_id,
            force_regenerate=payload.force_regenerate,
            override_voice_id=payload.voice_id,
            override_language=payload.language,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/shots/{shot_id}/mix-audio",
    response_model=ShotAudioMixResponse,
    status_code=status.HTTP_200_OK,
)
def mix_shot_audio_endpoint(
    project_id: UUID,
    shot_id: UUID,
    payload: ShotAudioMixRequest = ShotAudioMixRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mix generated character dialogue audio into the shot video with ambient ducking."""
    try:
        return mix_dialogue_into_shot_video(
            db=db,
            project_id=project_id,
            shot_id=shot_id,
            user_id=user.id,
            duck_ambient=payload.duck_ambient,
            ambient_volume=payload.ambient_volume,
            speech_volume=payload.speech_volume,
            force_remix=payload.force_remix,
        )
    except Exception as exc:
        _handle_service_error(exc)


@router.post(
    "/populate-dialogues",
    status_code=status.HTTP_200_OK,
)
def populate_dialogues_endpoint(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Map dialogues from approved screenplay scenes to storyboard shots."""
    try:
        return populate_dialogues_from_screenplay(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


# Direct /shots/{shot_id} convenience router
shot_router = APIRouter(
    prefix="/shots/{shot_id}",
    tags=["Production Studio"],
)


@shot_router.get(
    "/production-config",
    response_model=ProductionShotConfigResponse,
    status_code=status.HTTP_200_OK,
)
def get_shot_production_config_direct(
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve production configuration for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shot not found.",
        )
    try:
        return get_production_shot_config(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.put(
    "/production-config",
    response_model=ProductionShotConfigResponse,
    status_code=status.HTTP_200_OK,
)
def update_shot_production_config_direct(
    shot_id: UUID,
    payload: ProductionSettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update production settings for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shot not found.",
        )
    try:
        return update_production_shot_config(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.post(
    "/generate-video",
    response_model=VideoGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_single_shot_video_direct(
    shot_id: UUID,
    payload: VideoGenerateRequest = VideoGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate production video asset for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shot not found.",
        )
    try:
        return await generate_shot_video(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
            payload=payload,
        )
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.get(
    "/video-status",
    response_model=VideoGenerateResponse,
    status_code=status.HTTP_200_OK,
)
def get_shot_video_status_direct(
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get video generation status for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shot not found.",
        )
    try:
        cfg = get_production_shot_config(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
        )
        return {
            "shot_id": str(shot_id),
            "video_url": cfg.get("video_url"),
            "status": cfg.get("video_status", "pending"),
            "duration_seconds": (cfg.get("production_settings") or {}).get("duration_seconds", 4),
            "message": f"Status: {cfg.get('video_status')}",
        }
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.get(
    "/dialogues",
    response_model=list[DialogueItem],
    status_code=status.HTTP_200_OK,
)
def get_shot_dialogues_direct(
    shot_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve dialogues for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shot not found.")
    try:
        return get_shot_dialogues(db=db, project_id=shot.project_id, shot_id=shot_id, user_id=user.id)
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.put(
    "/dialogues",
    response_model=list[DialogueItem],
    status_code=status.HTTP_200_OK,
)
def update_shot_dialogues_direct(
    shot_id: UUID,
    payload: ShotDialogueUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update dialogues for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shot not found.")
    try:
        return update_shot_dialogues(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
            dialogues=payload.dialogues,
        )
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.post(
    "/generate-voice",
    response_model=DialogueVoiceGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_shot_voice_direct(
    shot_id: UUID,
    payload: DialogueVoiceGenerateRequest = DialogueVoiceGenerateRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Synthesize voice audio for a shot directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shot not found.")
    try:
        return await generate_shot_dialogue_voice(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
            dialogue_id=payload.dialogue_id,
            force_regenerate=payload.force_regenerate,
            override_voice_id=payload.voice_id,
            override_language=payload.language,
        )
    except Exception as exc:
        _handle_service_error(exc)


@shot_router.post(
    "/mix-audio",
    response_model=ShotAudioMixResponse,
    status_code=status.HTTP_200_OK,
)
def mix_shot_audio_direct(
    shot_id: UUID,
    payload: ShotAudioMixRequest = ShotAudioMixRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mix dialogue audio into shot video directly by shot_id."""
    from app.models.shot import Shot
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shot not found.")
    try:
        return mix_dialogue_into_shot_video(
            db=db,
            project_id=shot.project_id,
            shot_id=shot_id,
            user_id=user.id,
            duck_ambient=payload.duck_ambient,
            ambient_volume=payload.ambient_volume,
            speech_volume=payload.speech_volume,
            force_remix=payload.force_remix,
        )
    except Exception as exc:
        _handle_service_error(exc)


