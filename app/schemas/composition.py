from pydantic import BaseModel, ConfigDict, Field


class VideoComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_partial: bool = Field(
        default=False,
        description="Whether to compose available completed shots even if some project shots are still pending or failed.",
    )
    force_recompose: bool = Field(
        default=False,
        description="Whether to overwrite an existing composed video.",
    )


class ComposedShotSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_id: str
    scene_number: int
    shot_number: int
    video_url: str | None = None
    video_status: str = "pending"
    duration_seconds: float = 4.0


class VideoComposeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    status: str = Field(
        description="Composition status: 'pending', 'processing', 'completed', or 'failed'",
    )
    video_url: str | None = None
    total_shots: int = 0
    composed_shots: int = 0
    duration_seconds: float = 0.0
    resolution: str = "720p"
    message: str | None = None
    shots: list[ComposedShotSummary] = Field(default_factory=list)
