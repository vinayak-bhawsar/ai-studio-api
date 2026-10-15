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
from app.schemas.character import (
    CharacterGenerateRequest,
    CharacterImageGenerateRequest,
    CharacterImageGenerateResponse,
    CharacterImageItemResult,
    CharacterResponse,
    CharacterUpdateRequest,
)
from app.service.character_service import (
    delete_character_details,
    generate_character_images,
    generate_characters,
    get_character,
    get_characters,
    update_character_details,
)


router = APIRouter(
    prefix="/projects/{project_id}/characters",
    tags=["Characters"],
)


@router.post(
    "/generate",
    response_model=list[CharacterResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_project_characters(
    project_id: UUID,
    payload: CharacterGenerateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return await generate_characters(
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
    response_model=CharacterImageGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_project_character_images(
    project_id: UUID,
    payload: CharacterImageGenerateRequest = CharacterImageGenerateRequest(),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Generate reference images for all or specified characters in the project.
    Performs bounded concurrent generation, saves image files, and updates DB.
    """
    try:
        res = await generate_character_images(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=payload,
        )

        # If every character failed, raise an accurate HTTP status instead of falsely returning 200 OK
        if res.get("status") == "failed" and res.get("total_characters", 0) > 0:
            first_err = next((r["error"] for r in res.get("results", []) if r.get("error")), "All character image generations failed.")
            if "401" in first_err or "Authentication error" in first_err or "10000" in first_err:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Character image generation authentication failed: {first_err}",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Character image generation failed: {first_err}",
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
        print(f"CHARACTER IMAGE GENERATION ERROR: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate character images: {exc}",
        ) from exc


@router.post(
    "/{character_id}/generate-image",
    response_model=CharacterImageItemResult,
    status_code=status.HTTP_200_OK,
)
async def generate_single_character_image(
    project_id: UUID,
    character_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Generate or regenerate a reference image for a single character.
    """
    try:
        res = await generate_character_images(
            db=db,
            project_id=project_id,
            user_id=user.id,
            payload=CharacterImageGenerateRequest(
                character_ids=[str(character_id)],
                force_regenerate=True,
            ),
        )
        if res.get("results"):
            item = res["results"][0]
            if item.get("status") == "failed":
                err = item.get("error") or "Generation failed."
                if "401" in err or "Authentication error" in err or "10000" in err:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Character image generation authentication failed: {err}",
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Character image generation failed: {err}",
                )
            return item
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found.",
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
    response_model=list[CharacterResponse],
    status_code=status.HTTP_200_OK,
)
def get_project_characters(
    project_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return get_characters(
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
    "/{character_id}",
    response_model=CharacterResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_character(
    project_id: UUID,
    character_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return get_character(
            db=db,
            project_id=project_id,
            character_id=character_id,
            user_id=user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.put(
    "/{character_id}",
    response_model=CharacterResponse,
    status_code=status.HTTP_200_OK,
)
def update_project_character(
    project_id: UUID,
    character_id: UUID,
    payload: CharacterUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return update_character_details(
            db=db,
            project_id=project_id,
            character_id=character_id,
            user_id=user.id,
            content=payload,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_character(
    project_id: UUID,
    character_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        delete_character_details(
            db=db,
            project_id=project_id,
            character_id=character_id,
            user_id=user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc