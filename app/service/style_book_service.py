import uuid

from sqlalchemy.orm import Session

from app.repository.project_repo import get_project_by_id
from app.repository.style_book_repo import (
    create_style_book,
    get_style_book_by_project,
    update_style_book,
)
from app.schemas.stylebook import StyleBookContent
from app.service.external.llm_client import LLMClient, LLMRole


def _validate_project_access(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
):
    project = get_project_by_id(
        db,
        project_id=project_id,
        user_id=user_id,
    )

    if not project:
        raise ValueError(
            "Project not found."
        )

    return project


def _serialize_style_book(
    style_book,
) -> dict:
    return {
        "id": str(style_book.id),
        "project_id": str(style_book.project_id),
        "style_book": style_book.content,
        "created_at": style_book.created_at.isoformat(),
        "updated_at": style_book.updated_at.isoformat(),
    }


def get_style_book(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    style_book = get_style_book_by_project(
        db=db,
        project_id=project_id,
    )

    if style_book is None:
        return None

    return _serialize_style_book(style_book)


def save_style_book(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    content: StyleBookContent,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    existing_style_book = get_style_book_by_project(
        db=db,
        project_id=project_id,
    )

    content_data = content.model_dump()

    if existing_style_book:
        style_book = update_style_book(
            db=db,
            style_book=existing_style_book,
            content=content_data,
        )
    else:
        style_book = create_style_book(
            db=db,
            project_id=project_id,
            content=content_data,
        )

    db.commit()
    db.refresh(style_book)

    return _serialize_style_book(style_book)


async def generate_style_book(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    idea: str | None,
):
    _validate_project_access(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    creative_idea = (
        idea.strip()
        if idea and idea.strip()
        else "Create a cinematic visual style for this project."
    )

    messages = [
        {
            "role": "system",
            "content": """
You are an expert film director, cinematographer,
production designer, and visual development artist.

Create a professional cinematic Style Book from the
user's creative idea.

The Style Book will be used later for:

- character reference generation
- environment generation
- storyboard generation
- scene composition
- shot generation
- image generation
- video generation

The Style Book must define a consistent visual language
that can be reused across the entire project.

Do not create a story or screenplay.

Focus only on visual style, cinematic language,
composition, framing, camera behavior, lighting,
color, texture, and mood.

IMPORTANT:

The Style Book must contain practical production-ready
choices that can later be used as persistent project-wide
settings.

For composition and framing, explicitly define:

1. aspect_ratio
2. composition_rules
3. framing
4. composition
5. shot_scale
6. camera_angle

The aspect ratio must be a standard cinematic value such as:

- 16:9
- 9:16
- 1:1
- 4:3
- 2.39:1

Choose the aspect ratio that best fits the project.

The composition_rules must contain one or more clear
cinematic composition rules such as:

- rule_of_thirds
- center_framing
- golden_ratio
- symmetry
- negative_space
- dutch_angle
- auto_aesthetic

Only select rules that make sense for the creative idea.

The aesthetic preset must be a concise reusable visual
direction such as:

- cinematic
- anime
- noir
- cyberpunk
- documentary
- vintage_80s
- watercolor
- custom

Do not blindly use these values. Select the most
appropriate aesthetic for the project.

Framing should explain how subjects are positioned
inside the frame.

Composition should explain how visual elements are
organized.

Shot scale should use practical cinematic terminology
such as:

- extreme_wide
- wide
- medium_wide
- medium
- medium_close_up
- close_up
- extreme_close_up

Camera angle should use practical values such as:

- eye_level
- low_angle
- high_angle
- birds_eye
- worms_eye
- over_the_shoulder
- dutch_angle

Keep all values specific and useful for downstream
image and video generation.

Return only the requested structured output.
""",
        },
        {
            "role": "user",
            "content": f"""
Create a cinematic Style Book for this project idea:

{creative_idea}

Define all of the following:

1. Aesthetic
   - preset
   - description

2. Composition and Framing
   - aspect ratio
   - composition rules
   - framing
   - composition
   - shot scale
   - camera angle

3. Color Palette
   - dominant colors
   - color description
   - colors that should remain consistent across
     characters, environments, scenes, and shots

4. Lighting
   - lighting style
   - intensity
   - practical cinematic description

5. Camera Style
   - lens
   - movement
   - depth of field
   - cinematic camera description

6. Texture
   - visual texture
   - material/film characteristics

7. Mood
   - overall emotional and visual mood

Make every section specific, practical, cinematic,
and reusable for future image and video generation.

The result should behave like a persistent visual
direction document for the entire project, not merely
a generic AI description.
""",
        },
    ]

    llm_client = LLMClient()

    generated_data = await llm_client.generate_structured(
        messages=messages,
        schema=StyleBookContent.model_json_schema(),
        schema_name="style_book",
        role=LLMRole.CREATIVE,
        temperature=0.4,
    )

    style_book_content = StyleBookContent.model_validate(
        generated_data
    )

    existing_style_book = get_style_book_by_project(
        db=db,
        project_id=project_id,
    )

    content_data = style_book_content.model_dump()

    if existing_style_book:
        style_book = update_style_book(
            db=db,
            style_book=existing_style_book,
            content=content_data,
        )
    else:
        style_book = create_style_book(
            db=db,
            project_id=project_id,
            content=content_data,
        )

    db.commit()
    db.refresh(style_book)

    return _serialize_style_book(style_book)