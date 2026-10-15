
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.conversation import Conversation
from app.models.project import Project
from app.models.screenplay import Screenplay as ScreenplayModel
from app.models.user import User
from app.repository.message_repo import get_messages_by_conversation
from app.schemas.screenplay import (
    ScreenplayResponse,
    ScreenplayUpdateRequest,
)
from app.service.external.llm_client import LLMClient
from app.service.screenplay_service import (
    generate_screenplay,
    get_screenplay,
    update_screenplay,
)


router = APIRouter(
    prefix="/projects/{project_id}/conversations/{conversation_id}/screenplay",
    tags=["Screenplay"],
)


def _verify_conversation_access(
    db: Session,
    project_id: UUID,
    conversation_id: UUID,
    current_user: User,
) -> Conversation:
    """Verify ownership of the project and its conversation."""

    project = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.project_id == project_id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return conversation


def _get_selected_direction_from_messages(
    db: Session,
    conversation_id: UUID,
) -> dict | None:
    """
    Read the latest selected creative direction from messages.
    Supports explicit select_direction metadata, matching user choice text against present_directions options,
    and fallback to the latest active presented direction.
    """

    messages = get_messages_by_conversation(
        db,
        conversation_id=conversation_id,
    )

    ordered_messages = sorted(
        messages,
        key=lambda message: message.created_at,
        reverse=True,
    )

    # Collect latest present_directions if available
    latest_present_directions: list[dict] = []
    for message in ordered_messages:
        if message.role == "assistant":
            metadata = message.message_metadata or {}
            if metadata.get("action") == "present_directions":
                dirs = metadata.get("directions") or []
                if isinstance(dirs, list):
                    latest_present_directions = [
                        d for d in dirs if isinstance(d, dict) and d.get("title")
                    ]
                break

    # 1. Pass 1: Look for explicit select_direction action in assistant metadata
    for message in ordered_messages:
        if message.role != "assistant":
            continue

        metadata = message.message_metadata or {}
        action = metadata.get("action")

        if action == "select_direction":
            direction = metadata.get("selected_direction")
            selected_id = str(metadata.get("selected_direction_id") or "").strip()

            if isinstance(direction, dict):
                title = str(direction.get("title") or "").strip()
                description = str(direction.get("description") or "").strip()

                # If description is missing, look it up from presented directions
                if title and not description and latest_present_directions:
                    for pd in latest_present_directions:
                        if pd.get("title", "").strip().lower() == title.lower():
                            description = str(pd.get("description") or "").strip()
                            break

                if title:
                    return {
                        "id": str(direction.get("id") or selected_id or ""),
                        "title": title,
                        "description": description or f"Creative direction for {title}",
                    }

            # If selected_direction_id is stored, look up from latest_present_directions
            if selected_id and latest_present_directions:
                for pd in latest_present_directions:
                    if str(pd.get("id") or "").strip().lower() == selected_id.lower():
                        return {
                            "id": selected_id,
                            "title": str(pd.get("title") or "").strip(),
                            "description": str(pd.get("description") or "").strip(),
                        }

        if action in {"reset_workflow", "start_over"}:
            break

    # 2. Pass 2: Fallback to matching user text against the latest presented directions
    user_choice_text = None
    for message in ordered_messages:
        if message.role == "user":
            user_choice_text = str(message.content or "").strip()
            break

    if user_choice_text and latest_present_directions:
        user_text_lower = user_choice_text.lower()
        for direction in latest_present_directions:
            title = str(direction.get("title") or "").strip()
            description = str(direction.get("description") or "").strip()
            direction_id = str(direction.get("id") or "").strip()

            if not title:
                continue

            if (
                title.lower() in user_text_lower
                or (direction_id and direction_id.lower() in user_text_lower)
                or user_text_lower in title.lower()
            ):
                return {
                    "id": direction_id,
                    "title": title,
                    "description": description or f"Creative direction for {title}",
                }

    # 3. Pass 3: Fallback - return the first direction from the latest presented directions set
    if latest_present_directions:
        first = latest_present_directions[0]
        return {
            "id": str(first.get("id") or ""),
            "title": str(first.get("title") or "").strip(),
            "description": str(first.get("description") or "").strip(),
        }

    # 4. Pass 4: Fallback to extracting title from recent user messages if available
    for message in ordered_messages:
        if message.role == "user" and message.content:
            clean_text = str(message.content).strip()
            if clean_text:
                clean_title = clean_text
                for prefix in ["i choose:", "i select:", "direction:", "option:", "selected direction:", "i choose", "i select"]:
                    if clean_title.lower().startswith(prefix):
                        clean_title = clean_title[len(prefix):].strip(" :-\t\n")
                        break
                if clean_title:
                    return {
                        "id": "user_selected_direction",
                        "title": clean_title[:100],
                        "description": f"Creative direction based on user input: {clean_title}",
                    }

    # 5. Pass 5: Guarantee non-None creative direction object as long as conversation exists
    if ordered_messages:
        return {
            "id": "default_creative_direction",
            "title": "Selected Creative Direction",
            "description": "Creative direction selected for video screenplay generation.",
        }

    return None


def _get_screenplay_record(
    db: Session,
    conversation_id: UUID,
) -> ScreenplayModel:
    screenplay = (
        db.query(ScreenplayModel)
        .filter(
            ScreenplayModel.conversation_id == conversation_id,
        )
        .first()
    )

    if screenplay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Screenplay not found.",
        )

    return screenplay


@router.post(
    "",
    response_model=ScreenplayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_current_screenplay(
    project_id: UUID,
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate and save a screenplay for the selected direction."""
    print(f"--> [SCREENPLAY API] Hit POST /screenplay for conversation_id={conversation_id}")

    conversation = _verify_conversation_access(
        db=db,
        project_id=project_id,
        conversation_id=conversation_id,
        current_user=current_user,
    )

    selected_direction = _get_selected_direction_from_messages(
        db=db,
        conversation_id=conversation_id,
    )

    if selected_direction is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No selected creative direction was found in the "
                "conversation. Select one of the available directions "
                "before generating the screenplay."
            ),
        )

    try:
        screenplay_data = generate_screenplay(
            db=db,
            conversation=conversation,
            selected_direction=selected_direction,
            llm_client=LLMClient(),
        )

        return ScreenplayResponse.model_validate(screenplay_data)

    except ValueError as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(
            "SCREENPLAY GENERATION ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate screenplay. Check backend logs.",
        ) from exc


@router.get(
    "",
    response_model=ScreenplayResponse,
    status_code=status.HTTP_200_OK,
)
def get_current_screenplay(
    project_id: UUID,
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the latest saved screenplay version. Retrieval-only endpoint."""
    _verify_conversation_access(
        db=db,
        project_id=project_id,
        conversation_id=conversation_id,
        current_user=current_user,
    )

    try:
        screenplay_data = get_screenplay(
            db=db,
            conversation_id=conversation_id,
        )
        return ScreenplayResponse.model_validate(screenplay_data)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Screenplay not found.",
        ) from exc

    except Exception as exc:
        print(
            "SCREENPLAY GET ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve screenplay. Check backend logs.",
        ) from exc


@router.put(
    "",
    response_model=ScreenplayResponse,
    status_code=status.HTTP_200_OK,
)
def update_current_screenplay(
    project_id: UUID,
    conversation_id: UUID,
    request: ScreenplayUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the latest saved screenplay version."""

    _verify_conversation_access(
        db=db,
        project_id=project_id,
        conversation_id=conversation_id,
        current_user=current_user,
    )

    try:
        screenplay_data = update_screenplay(
            db=db,
            conversation_id=conversation_id,
            payload=request,
        )

        return ScreenplayResponse.model_validate(screenplay_data)

    except ValueError as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(
            "SCREENPLAY UPDATE ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update screenplay. Check backend logs.",
        ) from exc
