from __future__ import annotations

import uuid
from pydantic import BaseModel, ConfigDict, Field


class DialogueItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    scene_id: str
    shot_id: str
    character_id: str | None = None
    character_name: str
    text: str = Field(min_length=1, max_length=5000)
    language: str = Field(default="en", description="Language code: 'en', 'hi', etc.")
    voice_id: str | None = Field(default=None, description="Assigned voice speaker ID")
    emotion_tone: str | None = Field(default=None, description="Emotional delivery style")
    start_time: float = Field(default=0.0, ge=0.0)
    duration_seconds: float | None = Field(default=None, ge=0.0)
    audio_url: str | None = None
    status: str = Field(default="pending", description="'pending', 'generating', 'completed', 'failed'")
    error: str | None = None


class ShotDialogueUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialogues: list[DialogueItem]


class DialogueVoiceGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialogue_id: str | None = Field(default=None, description="Specific dialogue ID to generate, or generate all if omitted")
    voice_id: str | None = None
    language: str | None = None
    force_regenerate: bool = False


class DialogueVoiceGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    shot_id: str
    total_dialogues: int
    completed_dialogues: int
    failed_dialogues: int
    dialogues: list[DialogueItem]
    message: str | None = None


class ShotAudioMixRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duck_ambient: bool = Field(default=True, description="Whether to duck background ambient audio during dialogue")
    ambient_volume: float = Field(default=0.25, ge=0.0, le=1.0, description="Volume level for ambient track when dialogue plays")
    speech_volume: float = Field(default=1.0, ge=0.0, le=2.0, description="Volume level for speech dialogue track")
    force_remix: bool = False


class ShotAudioMixResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    shot_id: str
    video_url: str
    has_dialogue: bool
    ambient_preserved: bool
    status: str
    message: str | None = None
