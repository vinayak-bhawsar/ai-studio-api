from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AgentAction = Literal[
    "ask_question",
    "present_directions",
    "select_direction",
]


class CreativeDirection(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    id: str = Field(
        min_length=1,
        max_length=100,
    )

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str = Field(
        min_length=1,
        max_length=2000,
    )


class AgentDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    action: AgentAction

    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    questions: list[str] = Field(
        default_factory=list,
        max_length=1,
    )

    directions: list[CreativeDirection] = Field(
        default_factory=list,
        max_length=3,
    )

    selected_direction_id: str | None = Field(
        default=None,
        max_length=100,
    )