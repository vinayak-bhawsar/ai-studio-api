from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ShotCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_number: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1, max_length=5000)
    action: str | None = Field(default=None, max_length=5000)
    camera_framing: str | None = Field(default=None, max_length=100)
    camera_movement: str | None = Field(default=None, max_length=100)
    camera_angle: str | None = Field(default=None, max_length=100)
    composition: str | None = Field(default=None, max_length=2000)
    cast_ids: list[UUID] | None = Field(default=None)
    start_frame_url: str | None = Field(default=None, max_length=1000)
    end_frame_url: str | None = Field(default=None, max_length=1000)


class ShotUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_number: int | None = Field(default=None, ge=1)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    action: str | None = Field(default=None, max_length=5000)
    camera_framing: str | None = Field(default=None, max_length=100)
    camera_movement: str | None = Field(default=None, max_length=100)
    camera_angle: str | None = Field(default=None, max_length=100)
    composition: str | None = Field(default=None, max_length=2000)
    cast_ids: list[UUID] | None = Field(default=None)
    start_frame_url: str | None = Field(default=None, max_length=1000)
    end_frame_url: str | None = Field(default=None, max_length=1000)
    generation_status: str | None = Field(default=None, max_length=50)


class ShotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    scene_id: str
    shot_number: int
    description: str
    action: str | None = None
    camera_framing: str | None = None
    camera_movement: str | None = None
    camera_angle: str | None = None
    composition: str | None = None
    cast_ids: list[str] = Field(default_factory=list)
    cast: list[dict] = Field(default_factory=list)
    start_frame_url: str | None = None
    end_frame_url: str | None = None
    generation_status: str = "pending"
    video_url: str | None = None
    video_status: str = "pending"
    production_settings: dict = Field(default_factory=dict)
    asset_metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class SceneCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int | None = Field(default=None, ge=1)
    heading: str = Field(min_length=1, max_length=500)
    time_of_day: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10000)
    narrative_purpose: str | None = Field(default=None, max_length=5000)
    environment_id: UUID | None = Field(default=None)
    cast_ids: list[UUID] | None = Field(default=None)
    source_screenplay_version_id: UUID | None = Field(default=None)


class SceneUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int | None = Field(default=None, ge=1)
    heading: str | None = Field(default=None, min_length=1, max_length=500)
    time_of_day: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=10000)
    narrative_purpose: str | None = Field(default=None, max_length=5000)
    environment_id: UUID | None = Field(default=None)
    cast_ids: list[UUID] | None = Field(default=None)


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_screenplay_version_id: str | None = None
    scene_number: int
    heading: str
    time_of_day: str | None = None
    description: str | None = None
    narrative_purpose: str | None = None
    environment_id: str | None = None
    environment: dict | None = None
    cast_ids: list[str] = Field(default_factory=list)
    cast: list[dict] = Field(default_factory=list)
    shots: list[ShotResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


class StoryboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    screenplay_version_id: str | None = None
    scenes: list[SceneResponse] = Field(default_factory=list)
    total_scenes: int = 0
    total_shots: int = 0


class StoryboardGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str | None = Field(default=None, max_length=2000)
    force_regenerate: bool = False


class ShotFrameGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_type: str = Field(default="start", pattern="^(start|end)$")
    instructions: str | None = Field(default=None, max_length=2000)
    force_regenerate: bool = False


class StoryboardFramesGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_ids: list[UUID] | None = None
    frame_type: str = Field(default="start", pattern="^(start|end)$")
    force_regenerate: bool = False
    instructions: str | None = Field(default=None, max_length=2000)


class FrameGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_id: str
    frame_type: str
    image_url: str | None = None
    status: str
    message: str | None = None
    character_identities: list[dict] | None = None


class StoryboardFramesGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    completed: int
    failed: int
    results: list[FrameGenerateResponse]


class ProductionSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_model: str | None = Field(default=None, max_length=100)
    duration_seconds: int | None = Field(default=None, ge=1, le=12)
    resolution: str | None = Field(default=None, pattern="^720p$")
    aspect_ratio: str | None = Field(default=None, pattern="^(16:9|9:16|1:1)$")
    fps: int | None = Field(default=None, ge=12, le=60)
    prompt_override: str | None = Field(default=None, max_length=5000)
    motion_intensity: str | None = Field(default=None, max_length=50)


class ProductionShotConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shot_id: str
    project_id: str
    scene_id: str
    shot_number: int
    start_frame_url: str | None = None
    end_frame_url: str | None = None
    video_url: str | None = None
    video_status: str = "pending"
    production_settings: dict = Field(default_factory=dict)
    has_start_frame: bool
    cast: list[dict] = Field(default_factory=list)
    environment: dict | None = None


class VideoGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_regenerate: bool = False
    duration_seconds: int | None = Field(default=None, ge=1, le=12)
    resolution: str | None = Field(default=None, pattern="^720p$")
    aspect_ratio: str | None = Field(default=None, pattern="^(16:9|9:16|1:1)$")
    instructions: str | None = Field(default=None, max_length=2000)
    require_start_frame: bool = False


class VideoGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_id: str
    video_url: str | None = None
    status: str
    duration_seconds: int = 4
    message: str | None = None


class BatchVideoGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_ids: list[UUID] | None = None
    force_regenerate: bool = False
    duration_seconds: int | None = Field(default=None, ge=1, le=12)
    resolution: str | None = Field(default=None, pattern="^720p$")
    aspect_ratio: str | None = Field(default=None, pattern="^(16:9|9:16|1:1)$")
    require_start_frame: bool = False


class BatchVideoGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    completed: int
    failed: int
    skipped: int
    results: list[VideoGenerateResponse]


class ProductionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    total_shots: int
    completed_videos: int
    generating_videos: int
    pending_videos: int
    failed_videos: int
    shots: list[dict] = Field(default_factory=list)
    composition: dict | None = None

