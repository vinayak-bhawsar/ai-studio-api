from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.repository.character_repo import (
    create_character,
    delete_character,
    get_character_by_id,
    get_character_by_name,
    get_latest_screenplay_version_by_project,
    list_characters,
    update_character,
)
from app.repository.project_repo import get_project_by_id
from app.schemas.character import (
    CharacterContent,
    CharacterImageGenerateRequest,
)
from app.service.external.image_client import ImageClient
from app.service.external.llm_client import LLMClient, LLMRole
from app.utils.image_storage import save_generated_image


def _validate_project_access(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
):
    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise ValueError(
            "Project not found."
        )

    return project


def _serialize_character(
    character,
) -> dict:
    return {
        "id": str(character.id),
        "project_id": str(character.project_id),
        "source_screenplay_version_id": (
            str(character.source_screenplay_version_id)
            if character.source_screenplay_version_id
            else None
        ),
        "name": character.name,
        "description": character.description,
        "role": character.role,
        "age": character.age,
        "appearance": character.appearance,
        "personality": character.personality,
        "wardrobe": character.wardrobe,
        "visual_style": character.visual_style,
        "reference_images": character.reference_images or [],
        "created_at": character.created_at.isoformat(),
        "updated_at": character.updated_at.isoformat(),
    }


def get_characters(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    characters = list_characters(
        db=db,
        project_id=project_id,
    )

    return [
        _serialize_character(character)
        for character in characters
    ]


def get_character(
    db: Session,
    project_id: uuid.UUID,
    character_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    character = get_character_by_id(
        db=db,
        character_id=character_id,
        project_id=project_id,
    )

    if character is None:
        raise ValueError(
            "Character not found."
        )

    return _serialize_character(character)


def update_character_details(
    db: Session,
    project_id: uuid.UUID,
    character_id: uuid.UUID,
    user_id: uuid.UUID,
    content: CharacterContent,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    character = get_character_by_id(
        db=db,
        character_id=character_id,
        project_id=project_id,
    )

    if character is None:
        raise ValueError(
            "Character not found."
        )

    existing_character = get_character_by_name(
        db=db,
        project_id=project_id,
        name=content.name,
    )

    if (
        existing_character
        and existing_character.id != character.id
    ):
        raise ValueError(
            "A character with this name already exists."
        )

    character = update_character(
        db=db,
        character=character,
        content=content.model_dump(),
    )

    db.commit()
    db.refresh(character)

    return _serialize_character(character)


def delete_character_details(
    db: Session,
    project_id: uuid.UUID,
    character_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    character = get_character_by_id(
        db=db,
        character_id=character_id,
        project_id=project_id,
    )

    if character is None:
        raise ValueError(
            "Character not found."
        )

    delete_character(
        db=db,
        character=character,
    )

    db.commit()


async def generate_characters(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    instructions: str | None,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    screenplay_version = get_latest_screenplay_version_by_project(
        db=db,
        project_id=project_id,
    )

    if screenplay_version is None:
        raise ValueError(
            "No screenplay exists for this project."
        )

    screenplay_content = screenplay_version.content

    screenplay_characters = screenplay_content.get(
        "characters",
        [],
    )

    if not screenplay_characters:
        raise ValueError(
            "No characters were found in the screenplay."
        )

    screenplay_context = "\n\n".join(
        (
            f"Character: {character.get('name', '')}\n"
            f"Description: {character.get('description', '')}"
        )
        for character in screenplay_characters
    )

    additional_instructions = (
        instructions.strip()
        if instructions and instructions.strip()
        else (
            "Create production-ready visual character "
            "profiles while preserving the screenplay."
        )
    )

    from app.service.visual_context_service import resolve_project_visual_context
    visual_context = resolve_project_visual_context(db=db, project_id=project_id)
    visual_context_block = visual_context.to_character_prompt_context()

    messages = [
        {
            "role": "system",
            "content": """
You are an expert character designer, costume designer, and casting director for film and video production.

Create production-ready character profiles from the supplied screenplay characters.

Important rules:

1. Do not invent unrelated characters.
2. Preserve every supplied character.
3. Preserve the character names.
4. Preserve the narrative role of each character.
5. Expand the descriptions into useful production specifications: physical appearance, personality, wardrobe, and visual style.
6. STRICT PROJECT BRIEF & CULTURAL ADHERENCE:
   - Characters' appearance, ethnicity, clothing, and wardrobe MUST authentically adhere to the PROJECT VISUAL CONTEXT.
   - If the project specifies traditional Indian wear, festival, or ethnic clothing, every character's wardrobe MUST specify authentic traditional garments (e.g. silk sarees, embroidered lehengas, kurtas, sherwanis, festive jewelry) and cultural details.
   - If the project specifies sci-fi, specify futuristic aerospace flight suits or cybernetic gear.
   - If the project specifies western fashion or corporate, specify contemporary designer or business attire.
   - DO NOT default to generic western corporate suits, modern office wear, or unrelated western tropes unless the project explicitly calls for it.
7. Respect all negative constraints and exclusions specified for this project.
8. Make the visual descriptions useful for future image and video generation.
9. Return only structured data.
""",
        },
        {
            "role": "user",
            "content": f"""
PROJECT VISUAL CONTEXT & CREATIVE BRIEF:
{visual_context_block}

Here are the characters from the latest screenplay:

{screenplay_context}

Additional instructions:

{additional_instructions}

Create the complete production character profiles matching this exact project context.
""",
        },
    ]

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "characters": {
                "type": "array",
                "minItems": 1,
                "items": CharacterContent.model_json_schema(),
            }
        },
        "required": [
            "characters",
        ],
    }

    llm_client = LLMClient()

    generated_data = await llm_client.generate_structured(
        messages=messages,
        schema=schema,
        schema_name="characters",
        role=LLMRole.CREATIVE,
        temperature=0.3,
    )

    generated_characters = generated_data.get(
        "characters",
        [],
    )

    if not generated_characters:
        raise ValueError(
            "AI did not generate any characters."
        )

    validated_characters = [
        CharacterContent.model_validate(
            character,
        )
        for character in generated_characters
    ]

    saved_characters = []

    for character_content in validated_characters:
        content = character_content.model_dump()

        existing_character = get_character_by_name(
            db=db,
            project_id=project_id,
            name=character_content.name,
        )

        if existing_character:
            existing_character.source_screenplay_version_id = (
                screenplay_version.id
            )

            character = update_character(
                db=db,
                character=existing_character,
                content=content,
            )
        else:
            character = create_character(
                db=db,
                project_id=project_id,
                source_screenplay_version_id=screenplay_version.id,
                content=content,
            )

        saved_characters.append(character)

    db.commit()

    for character in saved_characters:
        db.refresh(character)

    return [
        _serialize_character(character)
        for character in saved_characters
    ]


def build_character_image_prompt(
    character,
    visual_context: Any = None,
    style_book_context: str = "",
    instructions: str | None = None,
) -> str:
    """
    Construct a cinematic character portrait prompt matching the user's project creative brief.
    Synthesizes character profile with project-specific visual context (cultural background,
    authentic wardrobe styling, environment mood, and explicit negative constraints).
    Prevents generic corporate suits or Western office aesthetics from overriding the user's brief.
    """
    wardrobe_desc = character.wardrobe
    # If the character's legacy wardrobe explicitly contradicts project negative constraints, harmonize with authentic clothing
    if visual_context and getattr(visual_context, "negative_constraints", None) and wardrobe_desc:
        wardrobe_lower = wardrobe_desc.lower()
        is_conflicting = False
        for neg in visual_context.negative_constraints:
            neg_lower = neg.lower()
            if neg_lower in wardrobe_lower:
                is_conflicting = True
                break
            # Specifically check for business/formal corporate suit exclusions vs character wardrobe
            if re.search(r"\b(business|corporate|formal|office)\s+suit(s)?\b", neg_lower):
                # Only flag conflict if wardrobe explicitly mentions business/formal suit, NOT spacesuit, flight suit, wetsuit, etc.
                if re.search(r"\b(business suit|formal suit|corporate suit|office suit|necktie|tuxedo)\b", wardrobe_lower):
                    is_conflicting = True
                    break
        if is_conflicting and getattr(visual_context, "clothing_and_styling", None):
            wardrobe_desc = visual_context.clothing_and_styling

    prompt_parts = [
        f"Cinematic portrait of {character.name}.",
        f"Role: {character.role}.",
        f"Age: {character.age}.",
        f"Appearance: {character.appearance}.",
        f"Wardrobe: {wardrobe_desc}.",
        f"Visual style: {character.visual_style}.",
        f"Description: {character.description}.",
    ]

    if visual_context:
        if getattr(visual_context, "cultural_or_regional_context", None):
            prompt_parts.append(f"Cultural context: {visual_context.cultural_or_regional_context}.")
        if getattr(visual_context, "clothing_and_styling", None):
            prompt_parts.append(f"Authentic clothing and wardrobe: {visual_context.clothing_and_styling}.")
        if getattr(visual_context, "setting_and_environment", None):
            prompt_parts.append(f"Setting: {visual_context.setting_and_environment}.")
        if getattr(visual_context, "color_palette_and_mood", None):
            prompt_parts.append(f"Atmospheric mood and lighting: {visual_context.color_palette_and_mood}.")
        if getattr(visual_context, "product_or_subject", None):
            prompt_parts.append(f"Featured brand/product: {visual_context.product_or_subject}.")

    if style_book_context:
        prompt_parts.append(f"Project style: {style_book_context}.")

    if instructions and instructions.strip():
        prompt_parts.append(f"Additional instructions: {instructions.strip()}.")

    if visual_context and getattr(visual_context, "negative_constraints", None):
        neg_str = ", ".join(visual_context.negative_constraints)
        prompt_parts.append(f"Negative constraints, strictly avoid: {neg_str}.")

    prompt_parts.append(
        "Single person character portrait, 8k resolution, authentic character design, photorealistic, cinematic lighting."
    )
    return " ".join(prompt_parts)


async def generate_character_images(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: CharacterImageGenerateRequest | None = None,
    image_client: ImageClient | None = None,
) -> dict:
    """
    Generate character reference images using Gemini ImageClient.
    Persists generated image files and saves URLs in character reference_images array.
    Supports individual character processing so partial failures don't discard successful images.
    """
    import asyncio
    from pathlib import Path
    from app.core.config import settings
    from app.repository.style_book_repo import get_style_book_by_project
    from app.schemas.character import CharacterImageGenerateRequest
    from app.service.external.image_client import ImageClient
    from app.service.visual_context_service import resolve_project_visual_context

    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    req = payload or CharacterImageGenerateRequest()

    all_characters = list_characters(
        db=db,
        project_id=project_id,
    )

    if not all_characters:
        raise ValueError("No characters found for this project. Generate characters first.")

    target_characters = all_characters
    if req.character_ids:
        target_ids_set = {str(cid).strip().lower() for cid in req.character_ids}
        target_characters = [
            c for c in all_characters if str(c.id).strip().lower() in target_ids_set
        ]
        if not target_characters:
            raise ValueError("No matching characters found for the provided character IDs.")

    # Resolve project visual context (cultural context, clothing requirements, negative constraints)
    visual_context = resolve_project_visual_context(db=db, project_id=project_id)

    style_book_record = get_style_book_by_project(
        db=db,
        project_id=project_id,
    )

    style_book_context = ""
    if style_book_record and style_book_record.content:
        content = style_book_record.content
        if isinstance(content, dict):
            aesthetic = content.get("aesthetic", {})
            preset = aesthetic.get("preset") if isinstance(aesthetic, dict) else None
            color = content.get("color_palette", {})
            dominant = color.get("dominant_colors") if isinstance(color, dict) else None
            parts = []
            if preset:
                parts.append(f"Aesthetic: {preset}")
            if dominant:
                parts.append(f"Color palette: {dominant}")
            if parts:
                style_book_context = ", ".join(parts)

    output_dir = Path(getattr(settings, "IMAGE_GENERATION_OUTPUT_DIR", "generated-images")) / "characters" / str(project_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = image_client or ImageClient()
    semaphore = asyncio.Semaphore(3)

    async def process_character(character):
        async with semaphore:
            char_id_str = str(character.id)
            existing_images = list(character.reference_images or [])

            if existing_images and not req.force_regenerate:
                return {
                    "character_id": char_id_str,
                    "name": character.name,
                    "status": "skipped",
                    "image_url": existing_images[0],
                    "error": None,
                    "character": _serialize_character(character),
                }

            prompt = build_character_image_prompt(
                character=character,
                visual_context=visual_context,
                style_book_context=style_book_context,
                instructions=req.instructions,
            )

            try:
                gen_image = await client.generate_image(prompt)
                ext = "png" if "png" in getattr(gen_image, "mime_type", "").lower() else "jpg"
                image_url = save_generated_image(
                    project_id=project_id,
                    resource_type="characters",
                    resource_id=char_id_str,
                    image_bytes=gen_image.data,
                    extension=ext,
                )

                updated_refs = [image_url] + [img for img in existing_images if img != image_url]
                character.reference_images = updated_refs

                try:
                    db.commit()
                    db.refresh(character)
                except Exception:
                    db.rollback()
                    raise

                return {
                    "character_id": char_id_str,
                    "name": character.name,
                    "status": "success",
                    "image_url": image_url,
                    "error": None,
                    "character": _serialize_character(character),
                }

            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                err_detail = str(exc).strip() or repr(exc)
                print(f"CHARACTER IMAGE GENERATION FAILURE for {character.name} ({char_id_str}): {err_detail}")
                return {
                    "character_id": char_id_str,
                    "name": character.name,
                    "status": "failed",
                    "image_url": existing_images[0] if existing_images else None,
                    "error": err_detail,
                    "character": _serialize_character(character),
                }

    tasks = [process_character(c) for c in target_characters]
    results = await asyncio.gather(*tasks)

    successful_count = sum(1 for r in results if r["status"] == "success")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    total_count = len(results)

    if failed_count == 0:
        overall_status = "completed"
    elif successful_count == 0 and skipped_count == 0:
        overall_status = "failed"
    else:
        overall_status = "partial_success"

    return {
        "project_id": str(project_id),
        "status": overall_status,
        "total_characters": total_count,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "results": results,
    }