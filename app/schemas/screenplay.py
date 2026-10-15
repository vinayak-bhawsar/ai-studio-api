from pydantic import BaseModel, ConfigDict, Field


class DialogueLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character: str = Field(
        min_length=1,
        max_length=100,
    )

    line: str = Field(
        min_length=1,
        max_length=5000,
    )


class ScreenplayScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int = Field(
        ge=1,
    )

    heading: str = Field(
        min_length=1,
        max_length=500,
    )

    action: str = Field(
        min_length=1,
        max_length=10000,
    )

    dialogue: list[DialogueLine] = Field(
        ...,
        max_length=50,
    )


class ScreenplayCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=100,
    )

    description: str = Field(
        min_length=1,
        max_length=2000,
    )


class Screenplay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    logline: str = Field(
        min_length=1,
        max_length=2000,
    )

    characters: list[ScreenplayCharacter] = Field(
        ...,
        max_length=50,
    )

    scenes: list[ScreenplayScene] = Field(
        ...,
        min_length=1,
        max_length=100,
    )


class ScreenplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    version_id: str
    version: int
    is_locked: bool
    screenplay: Screenplay


class ScreenplayUpdateRequest(Screenplay):
    pass