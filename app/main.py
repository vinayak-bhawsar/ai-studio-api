from pathlib import Path
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.character import router as character_router
from app.api.conversation import router as conversation_router
from app.api.environment import router as environment_router
from app.api.message import router as message_router
from app.api.production import (
    router as production_router,
    shot_router as production_shot_router,
)
from app.api.project import router as project_router
from app.api.screenplay import router as screenplay_router
from app.api.storyboard import router as storyboard_router
from app.api.style_book import router as style_book_router
from app.core.config import settings
from app.utils.exceptions import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

app = FastAPI(
    title="AI Video Studio API",
    version="1.0.0",
)

output_dir = Path("generated-images")
output_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/generated-images",
    StaticFiles(directory=str(output_dir)),
    name="generated-images",
)

video_output_dir = Path("generated-videos")
video_output_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/generated-videos",
    StaticFiles(directory=str(video_output_dir)),
    name="generated-videos",
)

audio_output_dir = Path("generated-audio")
audio_output_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/generated-audio",
    StaticFiles(directory=str(audio_output_dir)),
    name="generated-audio",
)

# CORS configuration loaded from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX or None,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
)

# Exception handlers
app.add_exception_handler(
    StarletteHTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    Exception,
    general_exception_handler,
)

# Include routers
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(conversation_router)
app.include_router(message_router)
app.include_router(screenplay_router)
app.include_router(style_book_router)
app.include_router(character_router)
app.include_router(environment_router)
app.include_router(storyboard_router)
app.include_router(production_router)
app.include_router(production_shot_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "AI Video Studio backend is running",
    }