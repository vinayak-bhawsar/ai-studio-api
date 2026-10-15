from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProjectVisualContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_type: str = Field(
        default="general",
        description="Type of video: 'advertisement', 'short_film', 'documentary', 'reels', 'music_video', 'corporate', etc.",
    )
    purpose: str = Field(
        default="",
        description="Core intent, campaign goal, or narrative engine of the project.",
    )
    product_or_subject: str = Field(
        default="",
        description="The primary product, service, brand, or narrative subject being featured.",
    )
    target_audience: str = Field(
        default="",
        description="Intended audience, demographic, or cultural reach.",
    )
    cultural_or_regional_context: str = Field(
        default="",
        description="Specific cultural, geographical, ethnic, or regional world context requested.",
    )
    clothing_and_styling: str = Field(
        default="",
        description="Specific clothing, wardrobe, materials, patterns, traditional/modern attire, and styling requirements.",
    )
    setting_and_environment: str = Field(
        default="",
        description="Expected physical locations, architectural styles, props, and ambient world details.",
    )
    color_palette_and_mood: str = Field(
        default="",
        description="Color palette, lighting style, visual mood, and atmospheric tone.",
    )
    negative_constraints: list[str] = Field(
        default_factory=list,
        description="Explicit exclusions and negative visual constraints (e.g. no western suits for traditional ethnic ads).",
    )
    raw_user_brief: str = Field(
        default="",
        description="Summary of the user's raw creative instructions gathered from conversation messages and project settings.",
    )

    def to_character_prompt_context(self) -> str:
        """Format into a concise, high-impact instruction block for character design prompts."""
        lines = []
        if self.project_type and self.project_type != "general":
            lines.append(f"Project Format: {self.project_type.replace('_', ' ').title()}")
        if self.product_or_subject:
            lines.append(f"Featured Subject / Brand: {self.product_or_subject}")
        if self.cultural_or_regional_context:
            lines.append(f"Cultural Context: {self.cultural_or_regional_context}")
        if self.clothing_and_styling:
            lines.append(f"Required Wardrobe & Attire: {self.clothing_and_styling}")
        if self.setting_and_environment:
            lines.append(f"Setting: {self.setting_and_environment}")
        if self.color_palette_and_mood:
            lines.append(f"Visual Mood & Colors: {self.color_palette_and_mood}")
        if self.negative_constraints:
            lines.append(f"Strict Exclusions: absolutely no {', no '.join(self.negative_constraints)}")
        return "\n".join(lines)
