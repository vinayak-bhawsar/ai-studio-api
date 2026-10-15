from pydantic import BaseModel, ConfigDict, Field


class Aesthetic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=3000)


class CompositionAndFraming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: str = Field(min_length=1, max_length=20)
    composition_rules: list[str] = Field(min_length=1, max_length=10)
    framing: str = Field(min_length=1, max_length=1000)
    composition: str = Field(min_length=1, max_length=1000)
    shot_scale: str = Field(min_length=1, max_length=100)
    camera_angle: str = Field(min_length=1, max_length=100)


class ColorPalette(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: list[str] = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=3000)


class Lighting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: str = Field(min_length=1, max_length=500)
    intensity: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=3000)


class CameraStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lens: str = Field(min_length=1, max_length=200)
    movement: str = Field(min_length=1, max_length=500)
    depth_of_field: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=3000)


class Texture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=3000)


class StyleBookContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aesthetic: Aesthetic
    composition_and_framing: CompositionAndFraming
    color_palette: ColorPalette
    lighting: Lighting
    camera: CameraStyle
    texture: Texture
    mood: str = Field(min_length=1, max_length=1000)


class StyleBookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    style_book: StyleBookContent
    created_at: str
    updated_at: str


class StyleBookUpdateRequest(StyleBookContent):
    pass


class StyleBookGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idea: str | None = Field(
        default=None,
        max_length=10000,
    )