from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.repository.environment_repo import (
    create_environment,
    delete_environment,
    get_environment_by_id,
    get_environment_by_name,
    get_latest_screenplay_version_by_project,
    list_environments,
    update_environment,
)
from app.repository.project_repo import get_project_by_id
from app.schemas.environment import EnvironmentContent
from app.service.external.llm_client import LLMClient, LLMRole


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


def _serialize_environment(
    environment,
) -> dict:
    return {
        "id": str(environment.id),
        "project_id": str(environment.project_id),
        "source_screenplay_version_id": (
            str(environment.source_screenplay_version_id)
            if environment.source_screenplay_version_id
            else None
        ),
        "name": environment.name,
        "description": environment.description,
        "environment_type": environment.environment_type,
        "time_of_day": environment.time_of_day,
        "visual_description": environment.visual_description,
        "architecture": environment.architecture,
        "lighting": environment.lighting,
        "materials": environment.materials,
        "atmosphere": environment.atmosphere,
        "reference_images": environment.reference_images or [],
        "created_at": environment.created_at.isoformat(),
        "updated_at": environment.updated_at.isoformat(),
    }


def get_environments(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    environments = list_environments(
        db=db,
        project_id=project_id,
    )

    return [
        _serialize_environment(environment)
        for environment in environments
    ]


def get_environment(
    db: Session,
    project_id: uuid.UUID,
    environment_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    environment = get_environment_by_id(
        db=db,
        environment_id=environment_id,
        project_id=project_id,
    )

    if environment is None:
        raise ValueError(
            "Environment not found."
        )

    return _serialize_environment(environment)


def update_environment_details(
    db: Session,
    project_id: uuid.UUID,
    environment_id: uuid.UUID,
    user_id: uuid.UUID,
    content: EnvironmentContent,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    environment = get_environment_by_id(
        db=db,
        environment_id=environment_id,
        project_id=project_id,
    )

    if environment is None:
        raise ValueError(
            "Environment not found."
        )

    existing_environment = get_environment_by_name(
        db=db,
        project_id=project_id,
        name=content.name,
    )

    if (
        existing_environment
        and existing_environment.id != environment.id
    ):
        raise ValueError(
            "An environment with this name already exists."
        )

    environment = update_environment(
        db=db,
        environment=environment,
        content=content.model_dump(),
    )

    db.commit()
    db.refresh(environment)

    return _serialize_environment(environment)


def delete_environment_details(
    db: Session,
    project_id: uuid.UUID,
    environment_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    environment = get_environment_by_id(
        db=db,
        environment_id=environment_id,
        project_id=project_id,
    )

    if environment is None:
        raise ValueError(
            "Environment not found."
        )

    delete_environment(
        db=db,
        environment=environment,
    )

    db.commit()


async def generate_environments(
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

    scenes = screenplay_content.get(
        "scenes",
        [],
    )

    if not scenes:
        raise ValueError(
            "No scenes were found in the screenplay."
        )

    scene_context = "\n\n".join(
        (
            f"Scene {scene.get('scene_number', '')}\n"
            f"Heading: {scene.get('heading', '')}\n"
            f"Action: {scene.get('action', '')}"
        )
        for scene in scenes
    )

    additional_instructions = (
        instructions.strip()
        if instructions and instructions.strip()
        else (
            "Create production-ready environment profiles "
            "for all meaningful recurring locations."
        )
    )

    from app.service.visual_context_service import resolve_project_visual_context
    visual_context = resolve_project_visual_context(db=db, project_id=project_id)
    visual_context_block = visual_context.to_character_prompt_context()

    messages = [
        {
            "role": "system",
            "content": """
You are an expert production designer, environment designer, and cinematographer for film and video production.

Extract and develop production-ready environments from the supplied screenplay and project visual context.

An environment represents a meaningful physical location or world space that can be reused during production.

STRICT RULES:

1. Only create environments that are supported by the screenplay and the project's visual context.
2. STRICT VISUAL & CULTURAL CONSISTENCY:
   - Ensure architectural style, environment materials, decorative props, and lighting authentically reflect the project's cultural and narrative context.
   - For traditional or ethnic projects, describe authentic cultural architecture, festive decor, and appropriate settings rather than generic modern office cubicles.
   - For sci-fi projects, describe futuristic aerospace or cyberpunk spaces.
3. Respect all negative constraints and exclusions specified for this project.
4. Give every environment a specific, realistic name.
5. Never use placeholder values such as "string", "Environment", "Description", "Unknown", "N/A".
6. Describe environments in a way that is useful for image generation, video generation, and production design.
7. Return only structured data.
""",
        },
        {
            "role": "user",
            "content": f"""
PROJECT VISUAL CONTEXT:
{visual_context_block}

Here are the scenes from the latest screenplay:

{scene_context}

Additional instructions:

{additional_instructions}

Extract the meaningful production environments and create complete environment profiles.
""",
        },
    ]

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "environments": {
                "type": "array",
                "minItems": 1,
                "items": EnvironmentContent.model_json_schema(),
            }
        },
        "required": [
            "environments",
        ],
    }

    llm_client = LLMClient()

    generated_data = await llm_client.generate_structured(
        messages=messages,
        schema=schema,
        schema_name="environments",
        role=LLMRole.CREATIVE,
        temperature=0.3,
    )

    generated_environments = generated_data.get(
        "environments",
        [],
    )

    if not generated_environments:
        raise ValueError(
            "AI did not generate any environments."
        )

    validated_environments = [
        EnvironmentContent.model_validate(
            environment,
        )
        for environment in generated_environments
    ]

    saved_environments = []

    for environment_content in validated_environments:
        content = environment_content.model_dump()

        existing_environment = get_environment_by_name(
            db=db,
            project_id=project_id,
            name=environment_content.name,
        )

        if existing_environment:
            existing_environment.source_screenplay_version_id = (
                screenplay_version.id
            )

            environment = update_environment(
                db=db,
                environment=existing_environment,
                content=content,
            )
        else:
            environment = create_environment(
                db=db,
                project_id=project_id,
                source_screenplay_version_id=screenplay_version.id,
                content=content,
            )

        saved_environments.append(environment)

    db.commit()

    for environment in saved_environments:
        db.refresh(environment)

    return [
        _serialize_environment(environment)
        for environment in saved_environments
    ]


def build_environment_image_prompt(
    environment,
    visual_context: Any = None,
    style_book_context: str = "",
    scene_context: str = "",
    instructions: str | None = None,
) -> str:
    """
    Construct a cinematic environment concept art prompt using environment fields,
    project visual context, style book context, screenplay scene details, and optional user instructions.
    Focuses entirely on spatial layout, architecture, lighting, atmosphere, and visual style.
    """
    prompt_parts = [
        f"Cinematic environment establishing shot of {environment.name}.",
        f"Environment type: {environment.environment_type}.",
        f"Time of day: {environment.time_of_day}.",
        f"Description: {environment.description}.",
        f"Visual details: {environment.visual_description}.",
        f"Architecture and spatial layout: {environment.architecture}.",
        f"Lighting: {environment.lighting}.",
        f"Materials and textures: {environment.materials}.",
        f"Atmosphere and mood: {environment.atmosphere}.",
    ]

    if visual_context:
        if getattr(visual_context, "cultural_or_regional_context", None):
            prompt_parts.append(f"Cultural/regional architecture: {visual_context.cultural_or_regional_context}.")
        if getattr(visual_context, "setting_and_environment", None):
            prompt_parts.append(f"Project setting details: {visual_context.setting_and_environment}.")
        if getattr(visual_context, "color_palette_and_mood", None):
            prompt_parts.append(f"Color palette & mood: {visual_context.color_palette_and_mood}.")

    if style_book_context:
        prompt_parts.append(f"Project visual style: {style_book_context}.")

    if scene_context:
        prompt_parts.append(f"Screenplay scene context: {scene_context}.")

    if instructions and instructions.strip():
        prompt_parts.append(f"Additional instructions: {instructions.strip()}.")

    if visual_context and getattr(visual_context, "negative_constraints", None):
        neg_str = ", ".join(visual_context.negative_constraints)
        prompt_parts.append(f"Strict exclusions: absolutely no {neg_str}.")

    prompt_parts.append(
        "Cinematic wide angle establishing shot, production design location concept art, "
        "8k resolution, photorealistic, atmospheric lighting, architectural photography, "
        "no people in foreground, no character portraits."
    )

    return " ".join(prompt_parts)


async def generate_environment_images(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload=None,
    image_client=None,
) -> dict:
    """
    Generate environment concept images using Gemini ImageClient.
    Persists generated image files and saves URLs in environment reference_images array.
    Supports individual environment processing so partial failures don't discard successful images.
    """
    import asyncio
    from app.repository.style_book_repo import get_style_book_by_project
    from app.schemas.environment import EnvironmentImageGenerateRequest
    from app.service.external.image_client import ImageClient
    from app.utils.image_storage import save_generated_image

    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    req = payload or EnvironmentImageGenerateRequest()

    all_environments = list_environments(
        db=db,
        project_id=project_id,
    )

    if not all_environments:
        raise ValueError("No environments found for this project. Generate environments first.")

    target_environments = all_environments
    if req.environment_ids:
        target_ids_set = {str(eid).strip().lower() for eid in req.environment_ids}
        target_environments = [
            e for e in all_environments if str(e.id).strip().lower() in target_ids_set
        ]
        if not target_environments:
            raise ValueError("No matching environments found for the provided environment IDs.")

    # Retrieve style book context if present
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

    from app.service.visual_context_service import resolve_project_visual_context
    visual_context = resolve_project_visual_context(db=db, project_id=project_id)

    # Retrieve screenplay scene details if available
    screenplay_version = get_latest_screenplay_version_by_project(
        db=db,
        project_id=project_id,
    )
    scenes = []
    if screenplay_version and screenplay_version.content:
        content = screenplay_version.content
        if isinstance(content, dict):
            scenes = content.get("scenes", [])

    client = image_client or ImageClient()
    semaphore = asyncio.Semaphore(3)

    async def process_environment(environment):
        async with semaphore:
            env_id_str = str(environment.id)
            existing_images = list(environment.reference_images or [])

            if existing_images and not req.force_regenerate:
                return {
                    "environment_id": env_id_str,
                    "name": environment.name,
                    "status": "skipped",
                    "image_url": existing_images[0],
                    "error": None,
                    "environment": _serialize_environment(environment),
                }

            # Find matching scene context
            scene_context = ""
            env_name_lower = environment.name.lower()
            for s in scenes:
                heading = s.get("heading", "")
                action = s.get("action", "")
                if env_name_lower in heading.lower() or env_name_lower in action.lower():
                    scene_context = f"Scene {s.get('scene_number', '')}: {heading}. {action[:150]}"
                    break

            prompt = build_environment_image_prompt(
                environment=environment,
                visual_context=visual_context,
                style_book_context=style_book_context,
                scene_context=scene_context,
                instructions=req.instructions,
            )

            try:
                gen_image = await client.generate_image(prompt)

                image_url = save_generated_image(
                    project_id=project_id,
                    resource_type="environments",
                    resource_id=env_id_str,
                    image_bytes=gen_image.data,
                )

                updated_refs = [image_url] + [img for img in existing_images if img != image_url]
                environment.reference_images = updated_refs

                try:
                    db.commit()
                    db.refresh(environment)
                except Exception:
                    db.rollback()
                    raise

                return {
                    "environment_id": env_id_str,
                    "name": environment.name,
                    "status": "success",
                    "image_url": image_url,
                    "error": None,
                    "environment": _serialize_environment(environment),
                }

            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                err_detail = str(exc).strip() or repr(exc)
                print(f"ENVIRONMENT IMAGE GENERATION FAILURE for {environment.name} ({env_id_str}): {err_detail}")
                return {
                    "environment_id": env_id_str,
                    "name": environment.name,
                    "status": "failed",
                    "image_url": existing_images[0] if existing_images else None,
                    "error": err_detail,
                    "environment": _serialize_environment(environment),
                }

    tasks = [process_environment(e) for e in target_environments]
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
        "total_environments": total_count,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "results": results,
    }