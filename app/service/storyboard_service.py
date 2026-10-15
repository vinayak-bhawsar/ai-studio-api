from __future__ import annotations

import asyncio
from datetime import datetime
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.environment import Environment
from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.repository.character_repo import (
    get_latest_screenplay_version_by_project,
    list_characters,
)
from app.repository.environment_repo import list_environments
from app.repository.project_repo import get_project_by_id
from app.repository.style_book_repo import get_style_book_by_project
from app.repository.storyboard_repo import (
    create_scene,
    create_shot,
    delete_scene,
    delete_shot,
    delete_storyboard_by_project,
    get_scene_by_id,
    get_shot_by_id,
    list_scenes_by_project,
    list_shots_by_scene,
    renumber_scenes,
    renumber_shots,
    update_scene,
    update_shot,
)
from app.schemas.storyboard import (
    SceneCreateRequest,
    SceneUpdateRequest,
    ShotCreateRequest,
    ShotFrameGenerateRequest,
    ShotUpdateRequest,
    StoryboardFramesGenerateRequest,
)
from app.service.external.image_client import ImageClient
from app.service.external.llm_client import LLMClient, LLMRole
from app.utils.image_storage import save_generated_image


def _validate_project_access(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found.")
    if project.user_id != user_id:
        raise PermissionError("Access forbidden to this project.")
    return project


def _validate_environment(
    db: Session,
    project_id: uuid.UUID,
    environment_id: uuid.UUID | None,
) -> Environment | None:
    if not environment_id:
        return None
    env = (
        db.query(Environment)
        .filter(
            Environment.id == environment_id,
            Environment.project_id == project_id,
        )
        .first()
    )
    if not env:
        raise ValueError(
            f"Environment {environment_id} does not belong to this project."
        )
    return env


def _validate_cast_ids(
    db: Session,
    project_id: uuid.UUID,
    cast_ids: list[uuid.UUID] | None,
) -> list[str]:
    if not cast_ids:
        return []
    valid_chars = list_characters(db, project_id)
    valid_ids = {str(c.id) for c in valid_chars}

    clean_ids = []
    for cid in cast_ids:
        cid_str = str(cid)
        if cid_str not in valid_ids:
            raise ValueError(
                f"Character {cid} does not belong to this project."
            )
        clean_ids.append(cid_str)
    return clean_ids


def _serialize_shot(
    shot: Shot,
    char_map: dict[str, Character] | None = None,
) -> dict[str, Any]:
    cast_list = []
    if char_map and shot.cast_ids:
        for cid in shot.cast_ids:
            char = char_map.get(str(cid))
            if char:
                cast_list.append(
                    {
                        "id": str(char.id),
                        "name": char.name,
                        "role": char.role,
                        "reference_images": char.reference_images or [],
                    }
                )

    return {
        "id": str(shot.id),
        "project_id": str(shot.project_id),
        "scene_id": str(shot.scene_id),
        "shot_number": shot.shot_number,
        "description": shot.description,
        "action": shot.action,
        "camera_framing": shot.camera_framing,
        "camera_movement": shot.camera_movement,
        "camera_angle": shot.camera_angle,
        "composition": shot.composition,
        "cast_ids": [str(c) for c in (shot.cast_ids or [])],
        "cast": cast_list,
        "start_frame_url": shot.start_frame_url,
        "end_frame_url": shot.end_frame_url,
        "generation_status": shot.generation_status or "pending",
        "video_url": shot.video_url,
        "video_status": shot.video_status or "pending",
        "production_settings": shot.production_settings or {},
        "asset_metadata": shot.asset_metadata or {},
        "created_at": shot.created_at.isoformat(),
        "updated_at": shot.updated_at.isoformat(),
    }


def _serialize_scene(
    scene: Scene,
    env_map: dict[str, Environment] | None = None,
    char_map: dict[str, Character] | None = None,
) -> dict[str, Any]:
    env_data = None
    if scene.environment_id and env_map:
        env = env_map.get(str(scene.environment_id))
        if env:
            env_data = {
                "id": str(env.id),
                "name": env.name,
                "description": env.description,
                "environment_type": env.environment_type,
                "time_of_day": env.time_of_day,
                "reference_images": env.reference_images or [],
            }

    cast_list = []
    if char_map and scene.cast_ids:
        for cid in scene.cast_ids:
            char = char_map.get(str(cid))
            if char:
                cast_list.append(
                    {
                        "id": str(char.id),
                        "name": char.name,
                        "role": char.role,
                        "reference_images": char.reference_images or [],
                    }
                )

    shots_serialized = [
        _serialize_shot(shot, char_map)
        for shot in (scene.shots or [])
    ]

    return {
        "id": str(scene.id),
        "project_id": str(scene.project_id),
        "source_screenplay_version_id": (
            str(scene.source_screenplay_version_id)
            if scene.source_screenplay_version_id
            else None
        ),
        "scene_number": scene.scene_number,
        "heading": scene.heading,
        "time_of_day": scene.time_of_day,
        "description": scene.description,
        "narrative_purpose": scene.narrative_purpose,
        "environment_id": (
            str(scene.environment_id) if scene.environment_id else None
        ),
        "environment": env_data,
        "cast_ids": [str(c) for c in (scene.cast_ids or [])],
        "cast": cast_list,
        "shots": shots_serialized,
        "created_at": scene.created_at.isoformat(),
        "updated_at": scene.updated_at.isoformat(),
    }


def _serialize_storyboard(
    project_id: uuid.UUID,
    screenplay_version_id: uuid.UUID | None,
    scenes: list[Scene],
    env_map: dict[str, Environment] | None = None,
    char_map: dict[str, Character] | None = None,
) -> dict[str, Any]:
    serialized_scenes = [
        _serialize_scene(scene, env_map, char_map)
        for scene in scenes
    ]
    total_shots = sum(len(s.get("shots", [])) for s in serialized_scenes)

    return {
        "project_id": str(project_id),
        "screenplay_version_id": (
            str(screenplay_version_id) if screenplay_version_id else None
        ),
        "scenes": serialized_scenes,
        "total_scenes": len(serialized_scenes),
        "total_shots": total_shots,
    }


# =========================================================================
# STORYBOARD GENERATION
# =========================================================================

def _infer_time_of_day(heading: str) -> str:
    h_upper = heading.upper()
    for tod in ["NIGHT", "DAY", "DUSK", "DAWN", "SUNSET", "SUNRISE", "EVENING", "MORNING", "AFTERNOON"]:
        if tod in h_upper:
            return tod
    return "DAY"


def _deterministic_shot_breakdown(
    scene_data: dict,
    env_id: uuid.UUID | None,
    cast_ids: list[str],
) -> list[dict]:
    """Fallback generator to create high-quality cinematic shots deterministically."""
    heading = scene_data.get("heading", "")
    action = scene_data.get("action", "")
    dialogues = scene_data.get("dialogue", [])

    shots = []
    # Shot 1: Establishing / Wide shot
    shots.append({
        "shot_number": 1,
        "description": f"Establishing wide shot of {heading}. Setting the atmosphere and spatial layout.",
        "action": action[:200] if action else "Scene opening.",
        "camera_framing": "Wide Shot",
        "camera_movement": "Slow Pan",
        "camera_angle": "Eye Level",
        "composition": "Cinematic wide composition establishing the environment depth and mood.",
        "cast_ids": cast_ids[:2],
    })

    # Shot 2: Medium shot of the main action
    shots.append({
        "shot_number": 2,
        "description": f"Medium shot capturing the primary action: {action[:250] if action else 'Characters interacting.'}",
        "action": action[:300] if action else "Characters engage in the scene.",
        "camera_framing": "Medium Shot",
        "camera_movement": "Static",
        "camera_angle": "Eye Level",
        "composition": "Balanced two-shot or subject framing with shallow depth of field.",
        "cast_ids": cast_ids,
    })

    # Shot 3: Close-up on dialogue or key emotional reaction
    if dialogues:
        first_diag = dialogues[0]
        char_speaking = first_diag.get("character", "Speaker")
        line = first_diag.get("line", "")
        shots.append({
            "shot_number": 3,
            "description": f"Close-up of {char_speaking} speaking: \"{line[:100]}\"",
            "action": f"{char_speaking} delivers key dialogue with focused emotional expression.",
            "camera_framing": "Close-Up",
            "camera_movement": "Handheld",
            "camera_angle": "Eye Level",
            "composition": "Tight portrait framing on character expression, soft background bokeh.",
            "cast_ids": cast_ids[:1],
        })

    # Shot 4: Resolving / Dynamic angle
    shots.append({
        "shot_number": len(shots) + 1,
        "description": f"Dynamic concluding shot as the scene develops toward its turning point.",
        "action": "Visual punctuation wrapping up the scene action.",
        "camera_framing": "Medium Close-Up",
        "camera_movement": "Tracking",
        "camera_angle": "Low Angle",
        "composition": "Dramatic dynamic angle emphasizing tension and narrative progression.",
        "cast_ids": cast_ids,
    })

    return shots


async def generate_storyboard(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    instructions: str | None = None,
    force_regenerate: bool = False,
    llm_client: LLMClient | None = None,
) -> dict:
    """
    Generate scenes and an ordered shot breakdown from the project's saved screenplay.
    Preserves screenplay consistency and character/environment references.
    Skips duplicate generation unless force_regenerate is requested.
    """
    _validate_project_access(db, project_id, user_id)

    screenplay_version = get_latest_screenplay_version_by_project(
        db=db,
        project_id=project_id,
    )
    if not screenplay_version:
        raise ValueError(
            "No screenplay exists for this project. Generate and save a screenplay first."
        )

    # Check for existing scenes
    existing_scenes = list_scenes_by_project(db, project_id)
    characters = list_characters(db, project_id)
    environments = list_environments(db, project_id)
    char_map = {str(c.id): c for c in characters}
    env_map = {str(e.id): e for e in environments}

    if existing_scenes and not force_regenerate:
        return _serialize_storyboard(
            project_id=project_id,
            screenplay_version_id=screenplay_version.id,
            scenes=existing_scenes,
            env_map=env_map,
            char_map=char_map,
        )

    # If force_regenerate, preserve existing generated frames where possible
    saved_frames_by_shot_key = {}
    if existing_scenes and force_regenerate:
        for sc in existing_scenes:
            for sh in (sc.shots or []):
                if sh.start_frame_url or sh.end_frame_url:
                    key = (sc.scene_number, sh.shot_number)
                    saved_frames_by_shot_key[key] = {
                        "start_frame_url": sh.start_frame_url,
                        "end_frame_url": sh.end_frame_url,
                        "generation_status": sh.generation_status,
                        "asset_metadata": sh.asset_metadata,
                    }
        delete_storyboard_by_project(db, project_id)
        db.flush()

    screenplay_content = screenplay_version.content or {}
    screenplay_scenes = screenplay_content.get("scenes", [])
    if not screenplay_scenes:
        raise ValueError("No scenes were found in the screenplay.")

    # Name-to-model lookup maps
    char_name_to_id = {c.name.strip().lower(): str(c.id) for c in characters}
    env_name_to_id = {e.name.strip().lower(): e.id for e in environments}

    # Style book context
    style_book = get_style_book_by_project(db, project_id)
    style_context = ""
    if style_book and style_book.content:
        content = style_book.content
        if isinstance(content, dict):
            aesthetic = content.get("aesthetic", {})
            style_context = f"Aesthetic: {aesthetic.get('preset', 'Cinematic')} - {aesthetic.get('description', '')}"

    # Try LLM structured shot breakdown
    parsed_breakdown = None
    try:
        client = llm_client or LLMClient()
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "scenes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "scene_number": {"type": "integer"},
                            "heading": {"type": "string"},
                            "time_of_day": {"type": "string"},
                            "description": {"type": "string"},
                            "narrative_purpose": {"type": "string"},
                            "environment_name": {"type": "string"},
                            "character_names": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "shots": {
                                "type": "array",
                                "minItems": 2,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "shot_number": {"type": "integer"},
                                        "description": {"type": "string"},
                                        "action": {"type": "string"},
                                        "camera_framing": {"type": "string"},
                                        "camera_movement": {"type": "string"},
                                        "camera_angle": {"type": "string"},
                                        "composition": {"type": "string"},
                                        "character_names": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": [
                                        "shot_number",
                                        "description",
                                        "camera_framing",
                                        "camera_movement",
                                        "camera_angle",
                                        "composition",
                                    ],
                                },
                            },
                        },
                        "required": [
                            "scene_number",
                            "heading",
                            "time_of_day",
                            "description",
                            "narrative_purpose",
                            "shots",
                        ],
                    },
                }
            },
            "required": ["scenes"],
        }

        scene_summaries = []
        for sc in screenplay_scenes:
            dialogue_text = " | ".join(
                f"{d.get('character')}: {d.get('line')}"
                for d in sc.get("dialogue", [])[:4]
            )
            scene_summaries.append(
                f"SCENE {sc.get('scene_number')}: {sc.get('heading')}\n"
                f"Action: {sc.get('action')}\n"
                f"Dialogue: {dialogue_text}"
            )

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are a master storyboard artist and cinematographer for an AI movie studio. "
                    "Analyze the screenplay scenes and break down each scene into a sequenced list of cinematic shots. "
                    "Provide specific camera framing (Wide Shot, Close-Up, Medium Shot, etc.), "
                    "camera movement (Static, Pan, Tracking, Crane, Handheld, etc.), "
                    "camera angle (Eye Level, Low Angle, High Angle, Dutch Angle), and composition notes. "
                    "Maintain strict continuity with the screenplay."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Screenplay Title: {screenplay_content.get('title', 'Movie')}\n"
                    f"Logline: {screenplay_content.get('logline', '')}\n"
                    f"Visual Style: {style_context}\n"
                    f"Available Cast: {', '.join(c.name for c in characters)}\n"
                    f"Available Environments: {', '.join(e.name for e in environments)}\n\n"
                    f"Scenes to break down:\n\n" + "\n\n".join(scene_summaries) + "\n\n"
                    f"Instructions: {instructions or 'Create standard cinematic coverage for each scene.'}"
                ),
            },
        ]

        result = await client.generate_structured(
            messages=prompt_messages,
            schema=schema,
            schema_name="storyboard_breakdown",
            role=LLMRole.CREATIVE,
            temperature=0.3,
            timeout=60.0,
        )
        parsed_breakdown = result.get("scenes")
    except Exception as exc:
        print(f"Storyboard LLM generation encountered: {exc}. Using deterministic fallback.")
        parsed_breakdown = None

    created_scenes = []

    for sc_idx, sc_data in enumerate(screenplay_scenes, start=1):
        heading = sc_data.get("heading", f"SCENE {sc_idx}")
        time_of_day = _infer_time_of_day(heading)

        # Match environment
        matched_env_id = None
        for env_name, eid in env_name_to_id.items():
            if env_name in heading.lower() or env_name in sc_data.get("action", "").lower():
                matched_env_id = eid
                break

        # Match characters in this scene
        scene_cast_ids = []
        action_text = sc_data.get("action", "").lower()
        dialogue_chars = [
            d.get("character", "").strip().lower()
            for d in sc_data.get("dialogue", [])
        ]
        for cname, cid in char_name_to_id.items():
            if cname in action_text or cname in dialogue_chars:
                if cid not in scene_cast_ids:
                    scene_cast_ids.append(cid)

        # Check if LLM output has this scene
        llm_scene = None
        if parsed_breakdown:
            for ls in parsed_breakdown:
                if ls.get("scene_number") == sc_idx:
                    llm_scene = ls
                    break

        if llm_scene:
            time_of_day = llm_scene.get("time_of_day") or time_of_day
            description = llm_scene.get("description") or sc_data.get("action")
            narrative_purpose = llm_scene.get("narrative_purpose")
            # If LLM specified environment name, check match
            if not matched_env_id and llm_scene.get("environment_name"):
                ename = llm_scene["environment_name"].strip().lower()
                matched_env_id = env_name_to_id.get(ename)
            # Add any characters named by LLM
            for cname in llm_scene.get("character_names", []):
                cid = char_name_to_id.get(cname.strip().lower())
                if cid and cid not in scene_cast_ids:
                    scene_cast_ids.append(cid)
            shots_to_create = llm_scene.get("shots", [])
        else:
            description = sc_data.get("action")
            narrative_purpose = f"Advance the narrative of scene {sc_idx}."
            shots_to_create = _deterministic_shot_breakdown(
                sc_data,
                matched_env_id,
                scene_cast_ids,
            )

        # Create Scene record
        scene_record = create_scene(
            db=db,
            project_id=project_id,
            scene_data={
                "source_screenplay_version_id": screenplay_version.id,
                "scene_number": sc_idx,
                "heading": heading,
                "time_of_day": time_of_day,
                "description": description,
                "narrative_purpose": narrative_purpose,
                "environment_id": matched_env_id,
                "cast_ids": scene_cast_ids,
            },
        )

        # Create Shots for Scene
        for sh_idx, sh_data in enumerate(shots_to_create, start=1):
            shot_cast = []
            if "character_names" in sh_data:
                for cname in sh_data["character_names"]:
                    cid = char_name_to_id.get(cname.strip().lower())
                    if cid and cid not in shot_cast:
                        shot_cast.append(cid)
            elif "cast_ids" in sh_data:
                shot_cast = sh_data["cast_ids"]
            else:
                shot_cast = scene_cast_ids

            cached_frame = saved_frames_by_shot_key.get((sc_idx, sh_idx), {})

            create_shot(
                db=db,
                project_id=project_id,
                scene_id=scene_record.id,
                shot_data={
                    "shot_number": sh_idx,
                    "description": sh_data.get("description", f"Shot {sh_idx}"),
                    "action": sh_data.get("action"),
                    "camera_framing": sh_data.get("camera_framing", "Medium Shot"),
                    "camera_movement": sh_data.get("camera_movement", "Static"),
                    "camera_angle": sh_data.get("camera_angle", "Eye Level"),
                    "composition": sh_data.get("composition", "Balanced cinematic framing"),
                    "cast_ids": shot_cast,
                    "start_frame_url": cached_frame.get("start_frame_url"),
                    "end_frame_url": cached_frame.get("end_frame_url"),
                    "generation_status": cached_frame.get("generation_status", "pending"),
                    "asset_metadata": cached_frame.get("asset_metadata", {}),
                },
            )

        created_scenes.append(scene_record)

    db.commit()

    # Re-query cleanly to load fresh relationships
    persisted_scenes = list_scenes_by_project(db, project_id)
    return _serialize_storyboard(
        project_id=project_id,
        screenplay_version_id=screenplay_version.id,
        scenes=persisted_scenes,
        env_map=env_map,
        char_map=char_map,
    )


def get_storyboard(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    _validate_project_access(db, project_id, user_id)
    screenplay_version = get_latest_screenplay_version_by_project(db, project_id)
    scenes = list_scenes_by_project(db, project_id)
    characters = list_characters(db, project_id)
    environments = list_environments(db, project_id)
    char_map = {str(c.id): c for c in characters}
    env_map = {str(e.id): e for e in environments}

    return _serialize_storyboard(
        project_id=project_id,
        screenplay_version_id=screenplay_version.id if screenplay_version else None,
        scenes=scenes,
        env_map=env_map,
        char_map=char_map,
    )


# =========================================================================
# SCENE OPERATIONS
# =========================================================================

def get_scene_details(
    db: Session,
    project_id: uuid.UUID,
    scene_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    _validate_project_access(db, project_id, user_id)
    scene = get_scene_by_id(db, scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    characters = list_characters(db, project_id)
    environments = list_environments(db, project_id)
    char_map = {str(c.id): c for c in characters}
    env_map = {str(e.id): e for e in environments}

    return _serialize_scene(scene, env_map, char_map)


def create_scene_entry(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: SceneCreateRequest,
) -> dict:
    _validate_project_access(db, project_id, user_id)

    _validate_environment(db, project_id, payload.environment_id)
    clean_cast_ids = _validate_cast_ids(db, project_id, payload.cast_ids)

    existing_scenes = list_scenes_by_project(db, project_id)
    target_number = payload.scene_number
    if target_number is None or target_number <= 0:
        target_number = len(existing_scenes) + 1

    scene_data = payload.model_dump()
    scene_data["scene_number"] = target_number
    scene_data["cast_ids"] = clean_cast_ids

    # If target_number already exists, shift subsequent
    for sc in existing_scenes:
        if sc.scene_number >= target_number:
            sc.scene_number += 1
    db.flush()

    scene = create_scene(db, project_id, scene_data)
    db.commit()
    renumber_scenes(db, project_id)
    db.commit()

    return get_scene_details(db, project_id, scene.id, user_id)


def update_scene_entry(
    db: Session,
    project_id: uuid.UUID,
    scene_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: SceneUpdateRequest,
) -> dict:
    _validate_project_access(db, project_id, user_id)
    scene = get_scene_by_id(db, scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    if payload.environment_id is not None:
        _validate_environment(db, project_id, payload.environment_id)
    if payload.cast_ids is not None:
        clean_cast_ids = _validate_cast_ids(db, project_id, payload.cast_ids)
    else:
        clean_cast_ids = None

    update_dict = payload.model_dump(exclude_unset=True)
    if clean_cast_ids is not None:
        update_dict["cast_ids"] = clean_cast_ids

    # If scene_number is being updated and conflicts, shift other scenes
    if payload.scene_number and payload.scene_number != scene.scene_number:
        other_scene = (
            db.query(Scene)
            .filter(
                Scene.project_id == project_id,
                Scene.scene_number == payload.scene_number,
                Scene.id != scene.id,
            )
            .first()
        )
        if other_scene:
            other_scene.scene_number = scene.scene_number
            db.flush()

    update_scene(db, scene, update_dict)
    db.commit()
    renumber_scenes(db, project_id)
    db.commit()

    return get_scene_details(db, project_id, scene.id, user_id)


def delete_scene_entry(
    db: Session,
    project_id: uuid.UUID,
    scene_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    _validate_project_access(db, project_id, user_id)
    scene = get_scene_by_id(db, scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    delete_scene(db, scene)
    db.commit()
    renumber_scenes(db, project_id)
    db.commit()


# =========================================================================
# SHOT OPERATIONS
# =========================================================================

def get_scene_shots(
    db: Session,
    project_id: uuid.UUID,
    scene_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[dict]:
    _validate_project_access(db, project_id, user_id)
    scene = get_scene_by_id(db, scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    characters = list_characters(db, project_id)
    char_map = {str(c.id): c for c in characters}
    shots = list_shots_by_scene(db, scene_id)
    return [_serialize_shot(sh, char_map) for sh in shots]


def create_shot_entry(
    db: Session,
    project_id: uuid.UUID,
    scene_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ShotCreateRequest,
) -> dict:
    _validate_project_access(db, project_id, user_id)
    scene = get_scene_by_id(db, scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    clean_cast = _validate_cast_ids(db, project_id, payload.cast_ids)
    existing_shots = list_shots_by_scene(db, scene_id)
    target_num = payload.shot_number
    if target_num is None or target_num <= 0:
        target_num = len(existing_shots) + 1

    for sh in existing_shots:
        if sh.shot_number >= target_num:
            sh.shot_number += 1
    db.flush()

    shot_dict = payload.model_dump()
    shot_dict["shot_number"] = target_num
    shot_dict["cast_ids"] = clean_cast

    shot = create_shot(db, project_id, scene_id, shot_dict)
    db.commit()
    renumber_shots(db, scene_id)
    db.commit()

    characters = list_characters(db, project_id)
    char_map = {str(c.id): c for c in characters}
    return _serialize_shot(shot, char_map)


def get_shot_details(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    characters = list_characters(db, project_id)
    char_map = {str(c.id): c for c in characters}
    return _serialize_shot(shot, char_map)


def update_shot_entry(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ShotUpdateRequest,
) -> dict:
    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    if payload.cast_ids is not None:
        clean_cast = _validate_cast_ids(db, project_id, payload.cast_ids)
    else:
        clean_cast = None

    update_dict = payload.model_dump(exclude_unset=True)
    if clean_cast is not None:
        update_dict["cast_ids"] = clean_cast

    if payload.shot_number and payload.shot_number != shot.shot_number:
        other_shot = (
            db.query(Shot)
            .filter(
                Shot.scene_id == shot.scene_id,
                Shot.shot_number == payload.shot_number,
                Shot.id != shot.id,
            )
            .first()
        )
        if other_shot:
            other_shot.shot_number = shot.shot_number
            db.flush()

    update_shot(db, shot, update_dict)
    db.commit()
    renumber_shots(db, shot.scene_id)
    db.commit()

    characters = list_characters(db, project_id)
    char_map = {str(c.id): c for c in characters}
    return _serialize_shot(shot, char_map)


def delete_shot_entry(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    scene_id = shot.scene_id
    delete_shot(db, shot)
    db.commit()
    renumber_shots(db, scene_id)
    db.commit()


# =========================================================================
# START-FRAME AND END-FRAME GENERATION
# =========================================================================

def build_shot_frame_prompt(
    shot: Shot,
    scene: Scene,
    environment: Environment | None = None,
    cast_characters: list[Character] | None = None,
    style_context: str = "",
    instructions: str | None = None,
    frame_type: str = "start",
    visual_context: Any = None,
    start_frame_url: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    from app.service.character_identity_service import build_consistent_character_prompt_block

    parts = []

    if frame_type == "end":
        parts.append(
            f"Cinematic end-frame / concluding frame of shot {shot.shot_number}."
        )
    else:
        parts.append(
            f"Cinematic establishing start-frame of shot {shot.shot_number}."
        )

    parts.append(f"Scene: {scene.heading}.")
    if scene.time_of_day:
        parts.append(f"Time of day: {scene.time_of_day}.")

    # Framing and camera angle
    framing_parts = []
    if shot.camera_framing:
        framing_parts.append(f"Framing: {shot.camera_framing}")
    if shot.camera_angle:
        framing_parts.append(f"Camera angle: {shot.camera_angle}")
    if shot.camera_movement:
        framing_parts.append(f"Movement: {shot.camera_movement}")
    if shot.composition:
        framing_parts.append(f"Composition: {shot.composition}")
    if framing_parts:
        parts.append(", ".join(framing_parts) + ".")

    # Environment
    if environment:
        parts.append(
            f"Environment location: {environment.name}. "
            f"Lighting: {environment.lighting}. "
            f"Visual details: {environment.visual_description}. "
            f"Atmosphere: {environment.atmosphere}."
        )

    # Character identity block with spatial separation and canonical anchors
    character_identities: list[dict[str, Any]] = []
    if cast_characters:
        char_prompt, character_identities = build_consistent_character_prompt_block(
            characters=cast_characters,
            shot=shot,
            is_end_frame=(frame_type == "end"),
            start_frame_url=start_frame_url,
        )
        if char_prompt:
            parts.append(char_prompt)

    # Shot-specific action and motion
    parts.append(f"Shot action & description: {shot.description}.")
    if shot.action:
        parts.append(f"Dynamic action: {shot.action}.")

    # Cultural & visual context styling
    if visual_context:
        if getattr(visual_context, "cultural_or_regional_context", None):
            parts.append(f"Cultural context: {visual_context.cultural_or_regional_context}.")
        if getattr(visual_context, "clothing_and_styling", None):
            parts.append(f"Authentic clothing styling: {visual_context.clothing_and_styling}.")
        if getattr(visual_context, "color_palette_and_mood", None):
            parts.append(f"Color mood & lighting: {visual_context.color_palette_and_mood}.")
        if getattr(visual_context, "setting_and_environment", None):
            parts.append(f"Setting atmosphere: {visual_context.setting_and_environment}.")

    if style_context:
        parts.append(f"Project Visual Style: {style_context}.")

    if instructions and instructions.strip():
        parts.append(f"Director notes: {instructions.strip()}.")

    # Negative constraints (strictly avoid facial distortion, inconsistent identity, corporate suits if traditional)
    negative_elements = [
        "facial distortion",
        "mismatched character identity",
        "face swapping",
        "blurry facial features",
        "deformed hands",
        "extra limbs",
        "low resolution",
    ]
    if visual_context and getattr(visual_context, "negative_constraints", None):
        negative_elements.extend(visual_context.negative_constraints)
    parts.append(f"Negative constraints, strictly avoid: {', '.join(dict.fromkeys(negative_elements))}.")

    parts.append(
        "Cinematic film capture, ultra-detailed 8k resolution, cinematic lighting, "
        "photorealistic, 16:9 widescreen composition, professional movie scene production capture."
    )

    return " ".join(parts), character_identities


async def generate_shot_frame(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ShotFrameGenerateRequest | None = None,
    image_client: ImageClient | None = None,
) -> dict:
    """
    Generate a start or end reference frame for a specific shot.
    Validates ownership, generates asset via ImageClient, persists to storage and DB.
    """
    from app.service.character_identity_service import (
        load_canonical_reference_bytes,
        resolve_shot_active_characters,
    )
    from app.service.visual_context_service import resolve_project_visual_context

    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    scene = get_scene_by_id(db, shot.scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    req = payload or ShotFrameGenerateRequest()
    frame_type = req.frame_type.lower()
    is_end = frame_type == "end"

    existing_url = shot.end_frame_url if is_end else shot.start_frame_url
    if existing_url and not req.force_regenerate:
        return {
            "shot_id": str(shot.id),
            "frame_type": frame_type,
            "image_url": existing_url,
            "status": "skipped",
            "message": "Reference frame already exists. Use force_regenerate to overwrite.",
        }

    # Gather environment context
    environment = (
        db.query(Environment).filter(Environment.id == scene.environment_id).first()
        if scene.environment_id
        else None
    )

    # Intelligently resolve active focal characters for this shot to prevent cast pollution
    all_chars = list_characters(db, project_id)
    cast_characters = resolve_shot_active_characters(shot, scene, all_chars)
    if cast_characters:
        shot.cast_ids = [str(c.id) for c in cast_characters]

    # Load canonical reference portrait data for conditioning
    primary_char = cast_characters[0] if cast_characters else None
    ref_bytes, ref_mime = None, None
    if primary_char:
        ref_bytes, ref_mime = load_canonical_reference_bytes(primary_char, project_id)

    style_book = get_style_book_by_project(db, project_id)
    style_context = ""
    if style_book and style_book.content:
        content = style_book.content
        if isinstance(content, dict):
            aesthetic = content.get("aesthetic", {})
            color = content.get("color_palette", {})
            style_context = f"{aesthetic.get('preset', '')}, palette: {color.get('dominant_colors', '')}"

    visual_context = resolve_project_visual_context(db, project_id)

    prompt, identity_dicts = build_shot_frame_prompt(
        shot=shot,
        scene=scene,
        environment=environment,
        cast_characters=cast_characters,
        style_context=style_context,
        instructions=req.instructions,
        frame_type=frame_type,
        visual_context=visual_context,
        start_frame_url=shot.start_frame_url,
    )

    client = image_client or ImageClient()
    shot.generation_status = "generating"
    db.commit()

    try:
        generated_image = await client.generate_image(
            prompt=prompt,
            reference_image_bytes=ref_bytes,
            reference_image_mime=ref_mime,
        )
        ext = "png" if "png" in generated_image.mime_type.lower() else "jpg"
        resource_id = f"{shot.id}_{frame_type}"
        saved_url = save_generated_image(
            project_id=project_id,
            resource_type="storyboard",
            resource_id=resource_id,
            image_bytes=generated_image.data,
            extension=ext,
        )

        metadata_key = f"{frame_type}_frame"
        current_meta = dict(shot.asset_metadata or {})
        current_meta[metadata_key] = {
            "url": saved_url,
            "prompt": prompt,
            "character_identities": identity_dicts,
            "canonical_reference_applied": bool(primary_char and primary_char.reference_images),
            "generated_at": datetime.utcnow().isoformat(),
        }
        shot.asset_metadata = current_meta

        if is_end:
            shot.end_frame_url = saved_url
        else:
            shot.start_frame_url = saved_url

        shot.generation_status = "completed"
        db.commit()
        db.refresh(shot)

        return {
            "shot_id": str(shot.id),
            "frame_type": frame_type,
            "image_url": saved_url,
            "character_identities": identity_dicts,
            "status": "completed",
            "message": f"Successfully generated {frame_type}-frame with consistent character identity.",
        }

    except Exception as exc:
        shot.generation_status = "failed" if not existing_url else "completed"
        db.commit()
        raise RuntimeError(f"Frame generation failed: {exc}") from exc


async def generate_storyboard_frames(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: StoryboardFramesGenerateRequest | None = None,
    image_client: ImageClient | None = None,
) -> dict:
    """
    Batch generate frames for all or specified shots in the storyboard.
    Uses concurrency bounding and preserves successful results even on partial failures.
    """
    _validate_project_access(db, project_id, user_id)
    req = payload or StoryboardFramesGenerateRequest()

    all_shots = (
        db.query(Shot)
        .filter(Shot.project_id == project_id)
        .order_by(Shot.scene_id.asc(), Shot.shot_number.asc())
        .all()
    )
    if not all_shots:
        raise ValueError("No shots found for this project. Generate storyboard first.")

    target_shots = all_shots
    if req.shot_ids:
        target_ids = {str(sid) for sid in req.shot_ids}
        target_shots = [s for s in all_shots if str(s.id) in target_ids]
        if not target_shots:
            raise ValueError("No matching shots found for the provided shot IDs.")

    semaphore = asyncio.Semaphore(3)
    results = []

    async def _process_shot(shot_item: Shot):
        async with semaphore:
            single_req = ShotFrameGenerateRequest(
                frame_type=req.frame_type,
                instructions=req.instructions,
                force_regenerate=req.force_regenerate,
            )
            try:
                res = await generate_shot_frame(
                    db=db,
                    project_id=project_id,
                    shot_id=shot_item.id,
                    user_id=user_id,
                    payload=single_req,
                    image_client=image_client,
                )
                return res
            except Exception as e:
                return {
                    "shot_id": str(shot_item.id),
                    "frame_type": req.frame_type,
                    "image_url": None,
                    "status": "failed",
                    "message": str(e),
                }

    tasks = [_process_shot(sh) for sh in target_shots]
    results = await asyncio.gather(*tasks)

    completed = sum(1 for r in results if r["status"] in ("completed", "skipped"))
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "total": len(results),
        "completed": completed,
        "failed": failed,
        "results": results,
    }
