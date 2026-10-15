from pydantic import BaseModel, ConfigDict, Field


class CharacterContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str = Field(
        min_length=1,
        max_length=5000,
    )

    role: str = Field(
        min_length=1,
        max_length=100,
    )

    age: str = Field(
        min_length=1,
        max_length=100,
    )

    appearance: str = Field(
        min_length=1,
        max_length=5000,
    )

    personality: str = Field(
        min_length=1,
        max_length=5000,
    )

    wardrobe: str = Field(
        min_length=1,
        max_length=5000,
    )

    visual_style: str = Field(
        min_length=1,
        max_length=5000,
    )


class CharacterResponse(CharacterContent):
    id: str
    project_id: str
    source_screenplay_version_id: str | None
    reference_images: list[str]
    created_at: str
    updated_at: str


class CharacterUpdateRequest(CharacterContent):
    pass


class CharacterGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str | None = Field(
        default=None,
        max_length=10000,
    )


class CharacterImageGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_ids: list[str] | None = Field(
        default=None,
        description="Optional subset of character IDs to generate images for. If None, targets all characters in the project.",
    )
    force_regenerate: bool = Field(
        default=False,
        description="If True, regenerates images even for characters that already have reference images.",
    )
    instructions: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional custom visual style instructions to append to the prompt.",
    )


class CharacterImageItemResult(BaseModel):
    character_id: str
    name: str
    status: str  # "success", "failed", "skipped"
    image_url: str | None = None
    error: str | None = None
    character: CharacterResponse | None = None


class CharacterImageGenerateResponse(BaseModel):
    project_id: str
    status: str  # "completed", "partial_success", "failed", "no_characters"
    total_characters: int
    successful_count: int
    failed_count: int
    skipped_count: int
    results: list[CharacterImageItemResult]