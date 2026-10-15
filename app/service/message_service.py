import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy.orm import Session

from app.repository.conversation_repo import (
    get_conversation_by_id,
)
from app.repository.message_repo import (
    create_message,
    get_messages_by_conversation,
)
from app.repository.project_repo import get_project_by_id
from app.schemas.agent import CreativeDirection
from app.schemas.message import (
    MessageCreateRequest,
    MessageResponse,
)
from app.service.ai_service import AIService


ai_service = AIService()


def _message_to_response(message) -> MessageResponse:
    return MessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        role=message.role,
        content=message.content,
        metadata=message.message_metadata,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _build_conversation_history(
    messages,
) -> list[dict]:
    """
    Build conversation history in chronological order.

    Repository ordering is not assumed.
    """

    ordered_messages = sorted(
        messages,
        key=lambda message: message.created_at,
    )

    return [
        {
            "role": message.role,
            "content": message.content,
            "metadata": message.message_metadata,
        }
        for message in ordered_messages
    ]


def _build_direction_context(
    directions: list[dict],
) -> list[dict]:
    return [
        {
            "id": direction["id"],
            "title": direction["title"],
        }
        for direction in directions
    ]


def _build_direction_metadata(
    directions: list[dict],
) -> list[dict]:
    return [
        {
            "id": direction["id"],
            "title": direction["title"],
            "description": direction["description"],
        }
        for direction in directions
    ]


def _get_active_directions(
    messages,
) -> list[dict]:
    """
    Get the newest valid creative-direction set.

    Creative directions are stored inside assistant message
    metadata. The repository ordering is not assumed.
    """

    ordered_messages = sorted(
        messages,
        key=lambda message: message.created_at,
        reverse=True,
    )

    for message in ordered_messages:
        if message.role != "assistant":
            continue

        metadata = message.message_metadata or {}

        if metadata.get("action") != "present_directions":
            continue

        directions = metadata.get("directions") or []

        if not isinstance(directions, list):
            continue

        valid_directions: list[dict] = []

        for direction in directions:
            if not isinstance(direction, dict):
                continue

            direction_id = direction.get("id")
            title = direction.get("title")
            description = direction.get("description")

            if not direction_id:
                continue

            if not title:
                continue

            if not description:
                continue

            valid_directions.append(
                {
                    "id": str(direction_id),
                    "title": str(title),
                    "description": str(description),
                }
            )

        if valid_directions:
            return valid_directions

    return []


def _resolve_ordinal_selection(
    content: str,
    directions: list[dict],
) -> dict | None:
    """
    Resolve selections such as:

    - first one
    - second option
    - choose the third
    - go with the last one
    """

    text = content.lower().strip()

    if (
        re.search(
            r"\blast\s+(one|option)\b",
            text,
        )
        or "go with the last" in text
        or "choose the last" in text
        or "pick the last" in text
    ):
        if directions:
            return directions[-1]

    ordinal_patterns = [
        (0, r"\b(first|1st)\b"),
        (1, r"\b(second|2nd)\b"),
        (2, r"\b(third|3rd)\b"),
        (3, r"\b(fourth|4th)\b"),
    ]

    selection_words = (
        "like",
        "prefer",
        "choose",
        "pick",
        "select",
        "want",
        "take",
        "option",
        "one",
        "go with",
    )

    for index, pattern in ordinal_patterns:
        if not re.search(
            pattern,
            text,
        ):
            continue

        if not any(
            word in text
            for word in selection_words
        ):
            continue

        if index < len(directions):
            return directions[index]

    return None


def _normalize_selection_text(
    value: str,
) -> str:
    """
    Normalize user text and direction titles before matching.
    """

    text = str(value).lower().strip()

    replacements = {
        "–": "-",
        "—": "-",
        "_": " ",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }

    for old_value, new_value in replacements.items():
        text = text.replace(
            old_value,
            new_value,
        )

    text = re.sub(
        r"[^\w\s-]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _looks_like_direction_selection(
    content: str,
) -> bool:
    """
    Detect whether the user is explicitly trying to select
    one of the currently displayed creative directions.
    """

    text = _normalize_selection_text(
        content
    )

    if not text:
        return False

    explicit_phrases = (
        "i choose",
        "i chose",
        "i select",
        "i selected",
        "i pick",
        "i picked",
        "i prefer",
        "i like",
        "i want",
        "let's go with",
        "lets go with",
        "go with",
        "choose",
        "chose",
        "select",
        "selected",
        "pick",
        "picked",
        "prefer",
    )

    if any(
        phrase in text
        for phrase in explicit_phrases
    ):
        return True

    ordinal_patterns = (
        r"\bfirst\b",
        r"\bsecond\b",
        r"\bthird\b",
        r"\bfourth\b",
        r"\b1st\b",
        r"\b2nd\b",
        r"\b3rd\b",
        r"\b4th\b",
        r"\blast one\b",
        r"\blast option\b",
    )

    return any(
        re.search(
            pattern,
            text,
        )
        for pattern in ordinal_patterns
    )


def _resolve_direction_by_title(
    content: str,
    directions: list[dict],
) -> dict | None:
    """
    Resolve a direction from its visible title.
    """

    text = _normalize_selection_text(
        content
    )

    if not text:
        return None

    normalized_directions: list[
        tuple[str, dict]
    ] = []

    for direction in directions:
        title = _normalize_selection_text(
            direction.get(
                "title",
                "",
            )
        )

        if title:
            normalized_directions.append(
                (
                    title,
                    direction,
                )
            )

    # Exact title match.
    for title, direction in normalized_directions:
        if text == title:
            return direction

    # Natural sentence containing the title.
    for title, direction in normalized_directions:
        if title in text:
            return direction

    return None


def _resolve_selected_direction(
    content: str,
    directions: list[dict],
) -> dict | None:
    """
    Resolve an explicit direction selection from the user.
    """

    if not directions:
        return None

    ordinal_direction = _resolve_ordinal_selection(
        content,
        directions,
    )

    if ordinal_direction:
        return ordinal_direction

    by_title = _resolve_direction_by_title(
        content,
        directions,
    )

    if by_title:
        return by_title

    text = _normalize_selection_text(content)
    if text:
        for direction in directions:
            norm_title = _normalize_selection_text(
                direction.get("title", "")
            )
            if norm_title and (norm_title in text or text in norm_title):
                return direction

    return None


def _resolve_direction_id(
    selected_direction_id: str | None,
    directions: list[dict],
) -> str | None:
    """
    Validate an AI-selected direction ID, title, or ordinal against active directions.
    """

    if not selected_direction_id or not directions:
        return None

    raw_id = str(selected_direction_id).strip().casefold()

    # 1. Direct ID match
    for direction in directions:
        if str(direction.get("id", "")).strip().casefold() == raw_id:
            return direction["id"]

    # 2. Title match (AI returned title instead of ID)
    for direction in directions:
        if str(direction.get("title", "")).strip().casefold() == raw_id:
            return direction["id"]

    # 3. Normalized title substring match
    for direction in directions:
        norm_title = _normalize_selection_text(direction.get("title", ""))
        if norm_title and (norm_title in raw_id or raw_id in norm_title):
            return direction["id"]

    # 4. Ordinal index match ("1", "2", "3", "dir_1", "direction_1")
    for index, direction in enumerate(directions, start=1):
        if raw_id in {str(index), f"dir_{index}", f"direction_{index}", f"direction {index}"}:
            return direction["id"]

    return None


def _sse_event(
    event: str,
    data: dict,
) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


async def create_conversation_message_stream(
    db: Session,
    *,
    project_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    data: MessageCreateRequest,
) -> AsyncGenerator[str, None]:

    # ---------------------------------------------------------
    # 1. Validate project
    # ---------------------------------------------------------

    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        yield _sse_event(
            "error",
            {
                "message": "Project not found.",
            },
        )
        return

    reasoning_steps: list[str] = []

    # ---------------------------------------------------------
    # 2. Validate conversation
    # ---------------------------------------------------------

    conversation = get_conversation_by_id(
        db,
        conversation_id=conversation_id,
        project_id=project_id,
    )

    if not conversation:
        yield _sse_event(
            "error",
            {
                "message": "Conversation not found.",
            },
        )
        return

    # ---------------------------------------------------------
    # 3. Validate user message
    # ---------------------------------------------------------

    content = data.content.strip()

    if not content:
        yield _sse_event(
            "error",
            {
                "message": "Message content cannot be empty.",
            },
        )
        return

    # ---------------------------------------------------------
    # 4. Save user message
    # ---------------------------------------------------------

    user_message = create_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=content,
    )

    yield _sse_event(
        "message_start",
        {
            "message_id": str(
                user_message.id
            ),
            "conversation_id": str(
                conversation_id
            ),
            "conversation_title": conversation.title,
        },
    )

    # ---------------------------------------------------------
    # 5. Load conversation messages
    # ---------------------------------------------------------

    messages = get_messages_by_conversation(
        db,
        conversation_id=conversation_id,
    )

    conversation_history = (
        _build_conversation_history(
            messages
        )
    )

    # ---------------------------------------------------------
    # 6. Get active creative directions
    # ---------------------------------------------------------

    active_directions = _get_active_directions(
        messages
    )

    direction_context = _build_direction_context(
        active_directions
    )

    # ---------------------------------------------------------
    # 7. Reasoning event
    # ---------------------------------------------------------

    if "Understanding your request" not in reasoning_steps:
        reasoning_steps.append("Understanding your request")
    yield _sse_event(
        "reasoning",
        {
            "status": "Understanding your request",
            "steps": reasoning_steps,
        },
    )

    # ---------------------------------------------------------
    # 8. Deterministic direction selection
    # ---------------------------------------------------------

    deterministic_direction = (
        _resolve_selected_direction(
            content,
            active_directions,
        )
    )

    if deterministic_direction:

        _s_match = "Matching your selection with the active creative directions"
        if _s_match not in reasoning_steps:
            reasoning_steps.append(_s_match)
        yield _sse_event(
            "reasoning",
            {
                "status": _s_match,
                "steps": reasoning_steps,
            },
        )

        selected_direction = (
            deterministic_direction
        )

        assistant_content = (
            "You selected: "
            f"{selected_direction['title']}."
        )

        # -----------------------------------------------------
        # Move workflow to screenplay stage
        # -----------------------------------------------------

        conversation.stage = "screenplay"

        db.commit()
        db.refresh(conversation)

        # -----------------------------------------------------
        # Stream assistant content
        # -----------------------------------------------------

        yield _sse_event(
            "content",
            {
                "content": assistant_content,
            },
        )

        # -----------------------------------------------------
        # Save assistant selection state
        # -----------------------------------------------------

        assistant_metadata = {
            "action": "select_direction",
            "directions": [],
            "selected_direction_id": (
                selected_direction["id"]
            ),
            "selected_direction": selected_direction,
        }

        assistant_message = create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            metadata=assistant_metadata,
        )

        # -----------------------------------------------------
        # Finish SSE stream
        # -----------------------------------------------------

        yield _sse_event(
            "done",
            {
                "message_id": str(
                    assistant_message.id
                ),
                "action": "select_direction",
                "selected_direction_id": (
                    selected_direction["id"]
                ),
                "stage": conversation.stage,
                "conversation_title": conversation.title,
            },
        )

        return

    # ---------------------------------------------------------
    # 8.1 Prevent direction-regeneration loops
    #
    # If the user is clearly selecting a direction, ensure a direction is selected.
    # ---------------------------------------------------------

    if (
        active_directions
        and _looks_like_direction_selection(
            content
        )
    ):
        selected_direction = active_directions[0]

        _s_match = "Matching your selection with the active creative directions"
        if _s_match not in reasoning_steps:
            reasoning_steps.append(_s_match)
        yield _sse_event(
            "reasoning",
            {
                "status": _s_match,
                "steps": reasoning_steps,
            },
        )

        assistant_content = (
            "You selected: "
            f"{selected_direction['title']}."
        )

        conversation.stage = "screenplay"
        db.commit()
        db.refresh(conversation)

        yield _sse_event(
            "content",
            {
                "content": assistant_content,
            },
        )

        assistant_metadata = {
            "action": "select_direction",
            "directions": [],
            "selected_direction_id": selected_direction["id"],
            "selected_direction": selected_direction,
        }

        assistant_message = create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            metadata=assistant_metadata,
        )

        yield _sse_event(
            "done",
            {
                "message_id": str(assistant_message.id),
                "action": "select_direction",
                "selected_direction_id": selected_direction["id"],
                "stage": conversation.stage,
                "conversation_title": conversation.title,
            },
        )

        return

    # ---------------------------------------------------------
    # 9. AI response
    # ---------------------------------------------------------

    _s_dev = "Developing the creative response"
    if _s_dev not in reasoning_steps:
        reasoning_steps.append(_s_dev)
    yield _sse_event(
        "reasoning",
        {
            "status": _s_dev,
            "steps": reasoning_steps,
        },
    )

    user_msgs_count = sum(1 for m in messages if m.role == "user")
    is_first_user_message = user_msgs_count <= 1
    current_title = (conversation.title or "").strip()
    is_placeholder_title = not current_title or current_title in {
        "Creative Idea",
        "New Chat",
        "Script breakdown",
        "New Conversation",
        "Greeting",
        "Untitled",
    }
    should_generate_title = is_first_user_message or is_placeholder_title

    try:
        if should_generate_title:
            agent_res, generated_title = await asyncio.gather(
                ai_service.generate_response(
                    conversation_history=conversation_history,
                    stage=conversation.stage,
                    creative_directions=direction_context,
                ),
                ai_service.generate_conversation_title(content),
                return_exceptions=True,
            )
            if isinstance(agent_res, Exception):
                raise agent_res
            agent_decision = agent_res

            if isinstance(generated_title, str) and generated_title.strip():
                clean_title = generated_title.strip()
                if clean_title.lower() not in {"hi", "hello", "hey", "start", "new", "test"}:
                    conversation.title = clean_title
                    proj = project
                    if proj and (not proj.title or proj.title in {"Untitled Short", "Untitled", "New Project"}):
                        proj.title = clean_title
                    db.commit()
                    db.refresh(conversation)

                yield _sse_event(
                    "title",
                    {
                        "conversation_id": str(conversation_id),
                        "conversation_title": conversation.title,
                    },
                )
        else:
            agent_decision = (
                await ai_service.generate_response(
                    conversation_history=(
                        conversation_history
                    ),
                    stage=conversation.stage,
                    creative_directions=(
                        direction_context
                    ),
                )
            )

    except RuntimeError as exc:
        yield _sse_event(
            "error",
            {
                "message": str(exc),
            },
        )
        return

    # ---------------------------------------------------------
    # 10. Persist creative directions
    # ---------------------------------------------------------

    persisted_directions: list[dict] = []

    if (
        agent_decision.action
        == "present_directions"
    ):

        if len(
            agent_decision.directions
        ) != 3:
            yield _sse_event(
                "error",
                {
                    "message": (
                        "AI requested direction "
                        "presentation but did not return "
                        "exactly 3 directions."
                    ),
                },
            )
            return

        _s_dir = "Creating distinct creative directions"
        if _s_dir not in reasoning_steps:
            reasoning_steps.append(_s_dir)
        yield _sse_event(
            "reasoning",
            {
                "status": _s_dir,
                "steps": reasoning_steps,
            },
        )

        # Backend owns direction IDs for the current
        # conversation state.
        persisted_directions = [
            {
                "id": str(
                    uuid.uuid4()
                ),
                "title": direction.title,
                "description": direction.description,
            }
            for direction in agent_decision.directions
        ]

        agent_decision.directions = [
            CreativeDirection(
                id=direction["id"],
                title=direction["title"],
                description=direction["description"],
            )
            for direction in persisted_directions
        ]

    # ---------------------------------------------------------
    # 11. AI direction selection
    # ---------------------------------------------------------

    selected_direction: dict | None = None

    if (
        agent_decision.action
        == "select_direction"
    ):

        selected_direction_id = (
            _resolve_direction_id(
                agent_decision.selected_direction_id,
                active_directions,
            )
        )

        if selected_direction_id is None:
            deterministic_direction = (
                _resolve_selected_direction(
                    content,
                    active_directions,
                )
            )

            if deterministic_direction:
                selected_direction_id = (
                    deterministic_direction["id"]
                )

        # Fallback to first active direction or create on the fly from user text
        if not selected_direction:
            if active_directions:
                selected_direction = active_directions[0]
            else:
                title_match = re.sub(
                    r"^(i\s+(choose|chose|select|selected|pick|picked|want|prefer|like)|choose|select|pick|go\s+with)[:\s]*",
                    "",
                    content,
                    flags=re.IGNORECASE,
                ).strip()
                fallback_title = title_match if title_match else "Selected Direction"
                selected_direction = {
                    "id": str(uuid.uuid4()),
                    "title": fallback_title,
                    "description": f"Creative direction for {fallback_title}",
                }

        # -----------------------------------------------------
        # Move workflow to screenplay stage
        # -----------------------------------------------------

        conversation.stage = "screenplay"

        db.commit()
        db.refresh(conversation)

        agent_decision.selected_direction_id = (
            selected_direction["id"]
        )

        agent_decision.message = (
            "You selected: "
            f"{selected_direction['title']}."
        )

    # ---------------------------------------------------------
    # 12. Stream AI content
    # ---------------------------------------------------------

    yield _sse_event(
        "content",
        {
            "content": agent_decision.message,
        },
    )

    # ---------------------------------------------------------
    # 13. Build assistant metadata
    # ---------------------------------------------------------

    assistant_metadata = {
        "action": agent_decision.action,
        "reasoning_steps": reasoning_steps,
        "questions": (
            agent_decision.questions
            if agent_decision.action == "ask_question"
            else []
        ),
        "directions": (
            _build_direction_metadata(
                persisted_directions
            )
            if (
                agent_decision.action
                == "present_directions"
            )
            else []
        ),
        "selected_direction_id": (
            agent_decision.selected_direction_id
            if (
                agent_decision.action
                == "select_direction"
            )
            else None
        ),
        "selected_direction": (
            selected_direction
            if (
                agent_decision.action
                == "select_direction"
            )
            else None
        ),
    }

    # ---------------------------------------------------------
    # 14. Save assistant message
    # ---------------------------------------------------------

    assistant_message = create_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=agent_decision.message,
        metadata=assistant_metadata,
    )

    # ---------------------------------------------------------
    # 15. Finish SSE stream
    # ---------------------------------------------------------

    yield _sse_event(
        "done",
        {
            "message_id": str(
                assistant_message.id
            ),
            "action": agent_decision.action,
            "questions": (
                agent_decision.questions
                if agent_decision.action == "ask_question"
                else []
            ),
            "selected_direction_id": (
                agent_decision.selected_direction_id
            ),
            "directions": (
                _build_direction_metadata(
                    persisted_directions
                )
                if (
                    agent_decision.action
                    == "present_directions"
                )
                else []
            ),
            "stage": conversation.stage,
            "conversation_title": conversation.title,
        },
    )