import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scene import Scene
from app.models.shot import Shot


def get_scene_by_id(
    db: Session,
    scene_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> Scene | None:
    statement = select(Scene).where(Scene.id == scene_id)
    if project_id is not None:
        statement = statement.where(Scene.project_id == project_id)
    return db.scalar(statement)


def get_scene_by_number(
    db: Session,
    project_id: uuid.UUID,
    scene_number: int,
) -> Scene | None:
    statement = select(Scene).where(
        Scene.project_id == project_id,
        Scene.scene_number == scene_number,
    )
    return db.scalar(statement)


def list_scenes_by_project(
    db: Session,
    project_id: uuid.UUID,
) -> list[Scene]:
    statement = (
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(Scene.scene_number.asc())
    )
    return list(db.scalars(statement).all())


def create_scene(
    db: Session,
    project_id: uuid.UUID,
    scene_data: dict,
) -> Scene:
    cast_ids = [str(cid) for cid in scene_data.get("cast_ids", []) if cid]
    scene = Scene(
        id=scene_data.get("id") or uuid.uuid4(),
        project_id=project_id,
        source_screenplay_version_id=scene_data.get("source_screenplay_version_id"),
        scene_number=scene_data["scene_number"],
        heading=scene_data["heading"],
        time_of_day=scene_data.get("time_of_day"),
        description=scene_data.get("description"),
        narrative_purpose=scene_data.get("narrative_purpose"),
        environment_id=scene_data.get("environment_id"),
        cast_ids=cast_ids,
    )
    db.add(scene)
    db.flush()
    return scene


def update_scene(
    db: Session,
    scene: Scene,
    update_data: dict,
) -> Scene:
    for field in [
        "scene_number",
        "heading",
        "time_of_day",
        "description",
        "narrative_purpose",
        "environment_id",
    ]:
        if field in update_data and update_data[field] is not None:
            setattr(scene, field, update_data[field])

    if "cast_ids" in update_data and update_data["cast_ids"] is not None:
        scene.cast_ids = [str(cid) for cid in update_data["cast_ids"] if cid]

    db.flush()
    return scene


def delete_scene(
    db: Session,
    scene: Scene,
) -> None:
    db.delete(scene)
    db.flush()


def renumber_scenes(
    db: Session,
    project_id: uuid.UUID,
) -> None:
    scenes = list_scenes_by_project(db, project_id)
    # Temporary offset to avoid unique constraint violations
    for i, sc in enumerate(scenes):
        sc.scene_number = 10000 + i
    db.flush()

    for idx, sc in enumerate(scenes, start=1):
        sc.scene_number = idx
    db.flush()


def get_shot_by_id(
    db: Session,
    shot_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> Shot | None:
    statement = select(Shot).where(Shot.id == shot_id)
    if project_id is not None:
        statement = statement.where(Shot.project_id == project_id)
    return db.scalar(statement)


def get_shot_by_number(
    db: Session,
    scene_id: uuid.UUID,
    shot_number: int,
) -> Shot | None:
    statement = select(Shot).where(
        Shot.scene_id == scene_id,
        Shot.shot_number == shot_number,
    )
    return db.scalar(statement)


def list_shots_by_scene(
    db: Session,
    scene_id: uuid.UUID,
) -> list[Shot]:
    statement = (
        select(Shot)
        .where(Shot.scene_id == scene_id)
        .order_by(Shot.shot_number.asc())
    )
    return list(db.scalars(statement).all())


def list_shots_by_project(
    db: Session,
    project_id: uuid.UUID,
) -> list[Shot]:
    statement = (
        select(Shot)
        .where(Shot.project_id == project_id)
        .order_by(Shot.shot_number.asc())
    )
    return list(db.scalars(statement).all())


def create_shot(
    db: Session,
    project_id: uuid.UUID,
    scene_id: uuid.UUID,
    shot_data: dict,
) -> Shot:
    cast_ids = [str(cid) for cid in shot_data.get("cast_ids", []) if cid]
    shot = Shot(
        id=shot_data.get("id") or uuid.uuid4(),
        project_id=project_id,
        scene_id=scene_id,
        shot_number=shot_data["shot_number"],
        description=shot_data["description"],
        action=shot_data.get("action"),
        camera_framing=shot_data.get("camera_framing"),
        camera_movement=shot_data.get("camera_movement"),
        camera_angle=shot_data.get("camera_angle"),
        composition=shot_data.get("composition"),
        cast_ids=cast_ids,
        start_frame_url=shot_data.get("start_frame_url"),
        end_frame_url=shot_data.get("end_frame_url"),
        generation_status=shot_data.get("generation_status", "pending"),
        asset_metadata=shot_data.get("asset_metadata", {}),
    )
    db.add(shot)
    db.flush()
    return shot


def update_shot(
    db: Session,
    shot: Shot,
    update_data: dict,
) -> Shot:
    for field in [
        "shot_number",
        "description",
        "action",
        "camera_framing",
        "camera_movement",
        "camera_angle",
        "composition",
        "start_frame_url",
        "end_frame_url",
        "generation_status",
    ]:
        if field in update_data and update_data[field] is not None:
            setattr(shot, field, update_data[field])

    if "cast_ids" in update_data and update_data["cast_ids"] is not None:
        shot.cast_ids = [str(cid) for cid in update_data["cast_ids"] if cid]

    if "asset_metadata" in update_data and update_data["asset_metadata"] is not None:
        merged = dict(shot.asset_metadata or {})
        merged.update(update_data["asset_metadata"])
        shot.asset_metadata = merged

    db.flush()
    return shot


def delete_shot(
    db: Session,
    shot: Shot,
) -> None:
    db.delete(shot)
    db.flush()


def renumber_shots(
    db: Session,
    scene_id: uuid.UUID,
) -> None:
    shots = list_shots_by_scene(db, scene_id)
    for i, sh in enumerate(shots):
        sh.shot_number = 10000 + i
    db.flush()

    for idx, sh in enumerate(shots, start=1):
        sh.shot_number = idx
    db.flush()


def delete_storyboard_by_project(
    db: Session,
    project_id: uuid.UUID,
) -> None:
    scenes = list_scenes_by_project(db, project_id)
    for scene in scenes:
        db.delete(scene)
    db.flush()
