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
from app.schemas.stylebook import (
    StyleBookGenerateRequest,
    StyleBookResponse,
    StyleBookUpdateRequest,
)
from app.service.style_book_service import (
    generate_style_book,
    get_style_book,
    save_style_book,
)


router = APIRouter(
    prefix="/projects/{project_id}/style-book",
    tags=["Style Book"],
)


@router.get(
    "",
    response_model=StyleBookResponse,
    status_code=status.HTTP_200_OK,
)
def get_current_style_book(
    project_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        result = get_style_book(
            db=db,
            project_id=project_id,
            user_id=user.id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Style Book not found.",
        )

    return result


@router.put(
    "",
    response_model=StyleBookResponse,
    status_code=status.HTTP_200_OK,
)
def update_current_style_book(
    project_id: UUID,
    payload: StyleBookUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return save_style_book(
            db=db,
            project_id=project_id,
            user_id=user.id,
            content=payload,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/generate",
    response_model=StyleBookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_current_style_book(
    project_id: UUID,
    payload: StyleBookGenerateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return await generate_style_book(
            db=db,
            project_id=project_id,
            user_id=user.id,
            idea=payload.idea,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc