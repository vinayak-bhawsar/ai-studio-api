from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =========================================================
    # DATABASE
    # =========================================================

    DATABASE_URL: str

    # =========================================================
    # JWT
    # =========================================================

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # =========================================================
    # LLM PROVIDER
    # =========================================================

    LLM_PROVIDER: str = "groq"

    LLM_API_KEY: str

    LLM_BASE_URL: str

    # =========================================================
    # LLM MODELS
    # =========================================================

    CREATIVE_LLM_MODEL: str

    REASONING_LLM_MODEL: str

    # =========================================================
    # CLOUDFLARE & MEDIA PROVIDER
    # =========================================================

    CLOUDFLARE_ACCOUNT_ID: str = "71c431bf8477cdbb10c039a878cad12e"
    CLOUDFLARE_API_TOKEN: str = ""
    CLOUDFLARE_IMAGE_API_TOKEN: str = ""
    CLOUDFLARE_IMAGE_ACCOUNT_ID: str = ""
    CLOUDFLARE_VIDEO_API_TOKEN: str = ""
    CLOUDFLARE_VIDEO_ACCOUNT_ID: str = ""

    CLOUDFLARE_IMAGE_MODEL: str = "alibaba/qwen-image-3.0-pro"
    IMAGE_GENERATION_MODEL: str = "alibaba/qwen-image-3.0-pro"
    VIDEO_GENERATION_MODEL: str = "google/veo-3.1-fast"
    GEMINI_API_KEY: str = ""

    # =========================================================
    # CLOUDFLARE R2 STORAGE
    # =========================================================

    R2_ACCOUNT_ID: str = "7308a67f2ad0fc8a9047065dfa016bcb"
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_ENDPOINT: str = "https://7308a67f2ad0fc8a9047065dfa016bcb.r2.cloudflarestorage.com"
    R2_BUCKET: str = "westackai-demos"
    R2_PREFIX: str = "agenting-rag"
    R2_PUBLIC_URL: str = "https://pub-133e384175444480bdd308fbbb08d13b.r2.dev"

    # =========================================================
    # SETTINGS
    # =========================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()