from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.environment import (
    EnvironmentGenerateRequest,
    EnvironmentImageGenerateRequest,
    EnvironmentImageGenerateResponse,
    EnvironmentImageItemResult,
    EnvironmentImageSingleRequest,
    EnvironmentResponse,
    EnvironmentUpdateRequest,
)
from app.service.environment_service import (
    delete_environment_details,
    generate_environment_images,
    generate_environments,
    get_environment,
    get_environments,
    update_environment_details,
)


router = APIRouter(
    prefix="/projects/{project_id}/environments",
    tags=["Environments"],
)


@router.post(
    "/generate",
    response_model=list[EnvironmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_project_environments(
    project_id: UUID,
    payload: EnvironmentGenerateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return await generate_environments(
            db=db,
            project_id=project_id,
            user_id=user.id,
            instructions=payload.instructions,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/generate-images",
    response_model=EnvironmentImageGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_project_environment_images(
    project_id: UUID,
    payload: EnvironmentImageGenerateRequest = EnvironmentImageGenerateRequest(),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Generate concept images for all or specified environments in the project.
    Performs bounded concurrent generation, saves image files, and updates DB.
    """
    try:
        res = await generate_environment_images(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=payload,
        )

        # If every environment failed, raise an accurate HTTP status instead of falsely returning 200 OK
        if res.get("status") == "failed" and res.get("total_environments", 0) > 0:
            first_err = next((r["error"] for r in res.get("results", []) if r.get("error")), "All environment image generations failed.")
            if "401" in first_err or "Authentication error" in first_err or "10000" in first_err:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Environment image generation authentication failed: {first_err}",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Environment image generation failed: {first_err}",
            )

        return res

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        print(f"ENVIRONMENT IMAGE GENERATION ERROR: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate environment images: {exc}",
        ) from exc


@router.post(
    "/{environment_id}/generate-image",
    response_model=EnvironmentImageItemResult,
    status_code=status.HTTP_200_OK,
)
async def generate_single_environment_image(
    project_id: UUID,
    environment_id: UUID,
    force_regenerate: bool = False,
    payload: EnvironmentImageSingleRequest | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Generate or regenerate a concept image for a single environment.
    """
    try:
        is_force = force_regenerate
        instructions = None
        if payload is not None:
            if payload.force_regenerate:
                is_force = True
            if payload.instructions:
                instructions = payload.instructions

        res = await generate_environment_images(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=EnvironmentImageGenerateRequest(
                environment_ids=[str(environment_id)],
                force_regenerate=is_force,
                instructions=instructions,
            ),
        )
        if res.get("results"):
            item = res["results"][0]
            if item.get("status") == "failed":
                err = item.get("error") or "Generation failed."
                if "401" in err or "Authentication error" in err or "10000" in err:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Environment image generation authentication failed: {err}",
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Environment image generation failed: {err}",
                )
            return item
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found.",
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc



@router.get(
    "",
    response_model=list[EnvironmentResponse],
    status_code=status.HTTP_200_OK,
)
def get_project_environments(
    project_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return get_environments(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{environment_id}",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_environment(
    project_id: UUID,
    environment_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return get_environment(
            db=db,
            project_id=project_id,
            environment_id=environment_id,
            user_id=user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.put(
    "/{environment_id}",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_200_OK,
)
def update_project_environment(
    project_id: UUID,
    environment_id: UUID,
    payload: EnvironmentUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return update_environment_details(
            db=db,
            project_id=project_id,
            environment_id=environment_id,
            user_id=user.id,
            content=payload,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_environment(
    project_id: UUID,
    environment_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        delete_environment_details(
            db=db,
            project_id=project_id,
            environment_id=environment_id,
            user_id=user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc