from pydantic import BaseModel, ConfigDict, Field


class EnvironmentContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str = Field(
        min_length=1,
        max_length=5000,
    )

    environment_type: str = Field(
        min_length=1,
        max_length=100,
    )

    time_of_day: str = Field(
        min_length=1,
        max_length=100,
    )

    visual_description: str = Field(
        min_length=1,
        max_length=5000,
    )

    architecture: str = Field(
        min_length=1,
        max_length=5000,
    )

    lighting: str = Field(
        min_length=1,
        max_length=5000,
    )

    materials: str = Field(
        min_length=1,
        max_length=5000,
    )

    atmosphere: str = Field(
        min_length=1,
        max_length=5000,
    )


class EnvironmentResponse(EnvironmentContent):
    id: str
    project_id: str
    source_screenplay_version_id: str | None
    reference_images: list[str]
    created_at: str
    updated_at: str


class EnvironmentUpdateRequest(EnvironmentContent):
    pass


class EnvironmentGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str | None = Field(
        default=None,
        max_length=10000,
    )


class EnvironmentImageGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_ids: list[str] | None = Field(
        default=None,
        description="Optional subset of environment IDs to generate images for. If None, targets all environments in the project.",
    )
    force_regenerate: bool = Field(
        default=False,
        description="If True, regenerates images even for environments that already have reference images.",
    )
    instructions: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional custom visual style instructions to append to the prompt.",
    )


class EnvironmentImageSingleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_regenerate: bool = Field(
        default=False,
        description="If True, regenerates images even for environments that already have reference images.",
    )
    instructions: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional custom visual style instructions to append to the prompt.",
    )


class EnvironmentImageItemResult(BaseModel):
    environment_id: str
    name: str
    status: str  # "success", "failed", "skipped"
    image_url: str | None = None
    error: str | None = None
    environment: EnvironmentResponse | None = None


class EnvironmentImageGenerateResponse(BaseModel):
    project_id: str
    status: str  # "completed", "partial_success", "failed", "no_environments"
    total_environments: int
    successful_count: int
    failed_count: int
    skipped_count: int
    results: list[EnvironmentImageItemResult]