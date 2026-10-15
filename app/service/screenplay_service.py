from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.project import Project
from app.repository.screenplay_repo import (
    create_screenplay,
    create_screenplay_version,
    get_latest_screenplay_version,
    get_screenplay_by_conversation,
    update_screenplay_version,
)
from app.schemas.screenplay import (
    Screenplay,
    ScreenplayCharacter,
    ScreenplayScene,
    ScreenplayUpdateRequest,
)
from app.service.external.llm_client import LLMClient, LLMRole


INVALID_VALUES = {
    "string",
    "character",
    "description",
    "unknown",
    "undefined",
    "not specified",
    "n/a",
    "na",
}


def _is_invalid(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return not normalized or normalized in INVALID_VALUES


def _validate_generated_screenplay(screenplay: Screenplay) -> None:
    if _is_invalid(screenplay.title):
        raise ValueError("AI generated an invalid screenplay title.")
    if _is_invalid(screenplay.logline):
        raise ValueError("AI generated an invalid screenplay logline.")
    if not 2 <= len(screenplay.characters) <= 5:
        raise ValueError("AI must generate between 2 and 5 screenplay characters.")
    if not 3 <= len(screenplay.scenes) <= 4:
        raise ValueError("AI must generate between 3 and 4 screenplay scenes.")

    character_names = set()
    for character in screenplay.characters:
        if _is_invalid(character.name) or _is_invalid(character.description):
            raise ValueError("AI generated an invalid screenplay character.")
        normalized_name = character.name.strip().casefold()
        if normalized_name in character_names:
            raise ValueError(f"AI generated duplicate character name '{character.name}'.")
        character_names.add(normalized_name)

    for expected_number, scene in enumerate(screenplay.scenes, start=1):
        if scene.scene_number != expected_number:
            raise ValueError("Generated screenplay scene numbers must be sequential starting at 1.")
        if _is_invalid(scene.heading) or _is_invalid(scene.action):
            raise ValueError(f"AI generated an invalid heading or action for scene {scene.scene_number}.")
        for line in scene.dialogue:
            if _is_invalid(line.character) or _is_invalid(line.line):
                raise ValueError(f"AI generated invalid dialogue in scene {scene.scene_number}.")
            if line.character.strip().casefold() not in character_names:
                raise ValueError(
                    f"Dialogue references '{line.character}', who is not in the screenplay character list."
                )


def _build_header_schema() -> dict[str, Any]:
    """Small structured schema for the screenplay header and character list."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "logline": {"type": "string", "minLength": 1, "maxLength": 2000},
            "characters": {
                "type": "array",
                "minItems": 2,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 100},
                        "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                    },
                    "required": ["name", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "logline", "characters"],
        "additionalProperties": False,
    }


def _build_screenplay_schema() -> dict[str, Any]:
    """Flat JSON schema for complete screenplay generation."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "logline": {"type": "string", "minLength": 1, "maxLength": 2000},
            "characters": {
                "type": "array",
                "minItems": 2,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 100},
                        "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                    },
                    "required": ["name", "description"],
                    "additionalProperties": False,
                },
            },
            "scenes": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "scene_number": {"type": "integer", "minimum": 1},
                        "heading": {"type": "string", "minLength": 1, "maxLength": 500},
                        "action": {"type": "string", "minLength": 1, "maxLength": 10000},
                        "dialogue": {
                            "type": "array",
                            "maxItems": 50,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "character": {"type": "string", "minLength": 1, "maxLength": 100},
                                    "line": {"type": "string", "minLength": 1, "maxLength": 5000},
                                },
                                "required": ["character", "line"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["scene_number", "heading", "action", "dialogue"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "logline", "characters", "scenes"],
        "additionalProperties": False,
    }


def _direction_prompt(direction: dict) -> str:
    title = str(direction.get("title") or "").strip()
    description = str(direction.get("description") or "").strip()
    if not title or not description:
        raise ValueError("Selected creative direction must include a title and description.")
    return f"CREATIVE DIRECTION TITLE:\n{title}\n\nCREATIVE DIRECTION:\n{description}"


def _header_messages(direction_prompt: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an expert screenwriter. Create an original, cinematic film concept. "
                "Return only the requested JSON object. Never use placeholders such as string, "
                "Character, Description, Unknown, N/A, or empty values. Create 2 to 5 distinct "
                "characters with realistic names and specific, useful descriptions. The logline "
                "must describe the protagonist, goal, conflict, and stakes. Do not include scenes yet."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Develop the title, logline, and character list for a production-ready cinematic screenplay.\n\n"
                f"{direction_prompt}\n\n"
                "Make the characters distinct and suitable for a story with a clear beginning, conflict, and resolution."
            ),
        },
    ]


def _scene_messages(
    direction_prompt: str,
    title: str,
    logline: str,
    characters: list[dict[str, str]],
    scene_number: int,
    previous_scenes: list[dict[str, Any]],
    total_scenes: int,
) -> list[dict[str, str]]:
    import json

    previous_context = json.dumps(previous_scenes, ensure_ascii=False)
    character_context = json.dumps(characters, ensure_ascii=False)
    beats = {
        1: "Opening: establish the world, protagonist, tone, and the story's inciting problem.",
        2: "Escalation: complicate the goal, reveal meaningful information, and increase the stakes.",
        3: "Climax and resolution: bring the central conflict to a decisive, emotionally satisfying outcome.",
        4: "Optional epilogue: use only if it adds a meaningful final image or resolves a remaining thread.",
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a professional screenwriter creating one scene at a time. Return only one JSON scene. "
                "The scene must be filmable and specific: concrete location/time heading, visual action, and natural "
                "dialogue. Keep character names exactly consistent with the provided character list. Dialogue lines "
                "must only use listed character names. Avoid placeholders and generic filler. Maintain continuity."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write scene {scene_number} of {total_scenes} for this screenplay.\n\n"
                f"{direction_prompt}\n\nTITLE: {title}\nLOGLINE: {logline}\n"
                f"CHARACTERS: {character_context}\n"
                f"PREVIOUS SCENES (for continuity): {previous_context}\n\n"
                f"SCENE PURPOSE: {beats[scene_number]}\n\n"
                "Requirements: use the exact scene_number provided; use a proper heading such as INT. LOCATION - NIGHT "
                "or EXT. LOCATION - DAY; action should be cinematic and concrete; include 2 to 6 relevant dialogue lines "
                "when appropriate; every dialogue character must appear in the character list; advance the story and do not "
                "repeat previous scenes. Keep the scene compact enough to fit a single structured response."
            ),
        },
    ]


def generate_screenplay(
    db: Session,
    conversation: Conversation,
    selected_direction: dict,
    llm_client: LLMClient,
) -> dict:
    """Generate screenplay in structured output, validate, then persist version."""
    from app.service.visual_context_service import resolve_project_visual_context
    visual_context = resolve_project_visual_context(db=db, project_id=conversation.project_id)
    visual_block = f"\n\nPROJECT VISUAL CONTEXT & CREATIVE BRIEF:\n{visual_context.to_character_prompt_context()}" if visual_context else ""

    direction_prompt = _direction_prompt(selected_direction) + visual_block

    screenplay_schema = _build_screenplay_schema()

    print("--> [SCREENPLAY SERVICE] Starting screenplay generation...")
    try:
        print("--> [SCREENPLAY SERVICE] Calling LLM generate_structured_sync (single-call)...")
        response_data = llm_client.generate_structured_sync(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert cinematic screenwriter. Write a complete, production-ready "
                        "short screenplay strictly tailored to the chosen creative direction and project visual context. "
                        "Respect any valid genre, culture, setting, language, format, and tone requested by the user "
                        "(including but not limited to narrative drama, sci-fi, fantasy, horror, thriller, documentary, "
                        "comedy, animation/anime, action, historical, cultural/ethnic, promotional, educational, or musical). "
                        "Adapt precisely to the user's requested world without introducing unrelated tropes, and do NOT impose "
                        "corporate conventions, brand placements, or advertising structures unless explicitly requested in the brief. "
                        "Include a catchy title, compelling logline, 2 to 4 distinct main characters with visual descriptions, and exactly 3 "
                        "sequential cinematic scenes (Scene 1: Opening/Establish, Scene 2: Escalation/Conflict, "
                        "Scene 3: Climax/Resolution). Ensure headings follow standard format (INT. or EXT. LOCATION - TIME), "
                        "actions are vivid and visual, and dialogue uses listed character names."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Create a complete short screenplay for the following creative direction and project context:\n\n"
                        f"{direction_prompt}\n\n"
                        "Requirements:\n"
                        "- 2 to 4 main characters with concise visual descriptions matching the cultural and wardrobe context.\n"
                        "- Exactly 3 sequential scenes (scene_number: 1, 2, 3).\n"
                        "- All dialogue characters must match names listed in the characters array.\n"
                        "- Keep action and dialogue punchy and cinematic."
                    ),
                },
            ],
            schema=screenplay_schema,
            schema_name="complete_screenplay",
            role=LLMRole.CREATIVE,
            temperature=0.2,
            max_tokens=8192,
            timeout=120.0,
        )

        screenplay = Screenplay.model_validate(response_data)
        _validate_generated_screenplay(screenplay)
        print("--> [SCREENPLAY SERVICE] Single-call screenplay generation succeeded and passed validation!")

    except Exception as primary_error:
        print(f"--> [SCREENPLAY SERVICE] Single-call generation failed ({primary_error}). Falling back to multi-step assembly...")
        # Fallback to step-by-step assembly if single-call structured output fails schema validation
        header_data = llm_client.generate_structured_sync(
            messages=_header_messages(direction_prompt),
            schema=_build_header_schema(),
            schema_name="screenplay_header",
            role=LLMRole.CREATIVE,
            temperature=0.2,
            max_tokens=8192,
            timeout=120.0,
        )
        title = str(header_data.get("title") or "").strip()
        logline = str(header_data.get("logline") or "").strip()
        characters = [
            ScreenplayCharacter.model_validate(item).model_dump()
            for item in (header_data.get("characters") or [])
        ]
        if _is_invalid(title) or _is_invalid(logline):
            raise ValueError("AI generated an invalid screenplay title or logline.") from primary_error
        if not 2 <= len(characters) <= 5:
            raise ValueError("AI must generate between 2 and 5 screenplay characters.") from primary_error

        scenes: list[dict[str, Any]] = []
        total_scenes = 3
        for scene_number in range(1, total_scenes + 1):
            print(f"--> [SCREENPLAY SERVICE] Multi-step assembly: Generating scene {scene_number}/3...")
            scene_data = llm_client.generate_structured_sync(
                messages=_scene_messages(
                    direction_prompt=direction_prompt,
                    title=title,
                    logline=logline,
                    characters=characters,
                    scene_number=scene_number,
                    previous_scenes=scenes,
                    total_scenes=total_scenes,
                ),
                schema=ScreenplayScene.model_json_schema(),
                schema_name=f"screenplay_scene_{scene_number}",
                role=LLMRole.CREATIVE,
                temperature=0.2,
                max_tokens=8192,
                timeout=120.0,
            )
            scene_data["scene_number"] = scene_number
            scene = ScreenplayScene.model_validate(scene_data)
            scenes.append(scene.model_dump())

        screenplay = Screenplay.model_validate(
            {
                "title": title,
                "logline": logline,
                "characters": characters,
                "scenes": scenes,
            }
        )
        _validate_generated_screenplay(screenplay)
        print("--> [SCREENPLAY SERVICE] Multi-step assembly succeeded and passed validation!")

    existing_screenplay = get_screenplay_by_conversation(
        db=db,
        conversation_id=conversation.id,
    )
    screenplay_record = existing_screenplay or create_screenplay(
        db=db,
        conversation_id=conversation.id,
    )
    latest_version = get_latest_screenplay_version(
        db=db,
        screenplay_id=screenplay_record.id,
    )
    version_number = latest_version.version + 1 if latest_version else 1
    screenplay_version = create_screenplay_version(
        db=db,
        screenplay_id=screenplay_record.id,
        version=version_number,
        title=screenplay.title,
        logline=screenplay.logline,
        content=screenplay.model_dump(),
    )

    if screenplay.title and screenplay.title.strip():
        proj = db.get(Project, conversation.project_id)
        if proj and (not proj.title or proj.title in {"Untitled Short", "Untitled", "New Project"}):
            proj.title = screenplay.title.strip()
    conversation.stage = "screenplay"
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(screenplay_record)
    db.refresh(screenplay_version)
    return {
        "id": str(screenplay_record.id),
        "conversation_id": str(conversation.id),
        "version_id": str(screenplay_version.id),
        "version": screenplay_version.version,
        "is_locked": screenplay_version.is_locked,
        "screenplay": screenplay.model_dump(),
    }


def get_screenplay(db: Session, conversation_id: uuid.UUID) -> dict:
    screenplay_record = get_screenplay_by_conversation(
        db=db,
        conversation_id=conversation_id,
    )
    if not screenplay_record:
        raise ValueError("Screenplay not found.")
    latest_version = get_latest_screenplay_version(
        db=db,
        screenplay_id=screenplay_record.id,
    )
    if not latest_version:
        raise ValueError("Screenplay version not found.")
    screenplay_content = Screenplay.model_validate(latest_version.content)
    return {
        "id": str(screenplay_record.id),
        "conversation_id": str(conversation_id),
        "version_id": str(latest_version.id),
        "version": latest_version.version,
        "is_locked": latest_version.is_locked,
        "screenplay": screenplay_content.model_dump(),
    }


def update_screenplay(
    db: Session,
    conversation_id: uuid.UUID,
    payload: ScreenplayUpdateRequest,
) -> dict:
    screenplay_record = get_screenplay_by_conversation(
        db=db,
        conversation_id=conversation_id,
    )
    if not screenplay_record:
        raise ValueError("Screenplay not found.")
    latest_version = get_latest_screenplay_version(
        db=db,
        screenplay_id=screenplay_record.id,
    )
    if not latest_version:
        raise ValueError("Screenplay version not found.")
    if latest_version.is_locked:
        raise ValueError("This screenplay is locked and cannot be edited.")
    screenplay_content = Screenplay.model_validate(payload.model_dump())
    _validate_generated_screenplay(screenplay_content)
    updated_version = update_screenplay_version(
        db=db,
        screenplay_version=latest_version,
        title=screenplay_content.title,
        logline=screenplay_content.logline,
        content=screenplay_content.model_dump(),
    )
    db.commit()
    db.refresh(updated_version)
    return {
        "id": str(screenplay_record.id),
        "conversation_id": str(conversation_id),
        "version_id": str(updated_version.id),
        "version": updated_version.version,
        "is_locked": updated_version.is_locked,
        "screenplay": screenplay_content.model_dump(),
    }
