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
    # CORS
    # =========================================================

    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:5173,http://localhost:5174,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:5173,http://127.0.0.1:5174,"
        "https://ai-studio-frontend.dpkkmishra.workers.dev,https://ai-studio.500kb.com,"
        "https://ai.studio.500kb.com,https://ai-studio-frontend.vairagigoldi-9c3.workers.dev"
    )
    CORS_ALLOW_ORIGIN_REGEX: str = (
        r"https?://(localhost|127\.0\.0\.1|.*\.workers\.dev|.*\.500kb\.com)(:\d+)?"
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return []
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        origins = []
        for part in self.CORS_ORIGINS.replace("\n", ",").replace("\r", ",").split(","):
            cleaned = part.strip().strip("'\"")
            if cleaned:
                origins.append(cleaned)
        return origins

    @property
    def cors_methods_list(self) -> list[str]:
        if not self.CORS_ALLOW_METHODS or self.CORS_ALLOW_METHODS.strip() == "*":
            return ["*"]
        return [method.strip() for method in self.CORS_ALLOW_METHODS.split(",") if method.strip()]

    @property
    def cors_headers_list(self) -> list[str]:
        if not self.CORS_ALLOW_HEADERS or self.CORS_ALLOW_HEADERS.strip() == "*":
            return ["*"]
        return [header.strip() for header in self.CORS_ALLOW_HEADERS.split(",") if header.strip()]

    # =========================================================
    # SETTINGS
    # =========================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()