import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Info
    APP_NAME: str = "Indian Financial Document Classification Engine"
    APP_ENV: str = "production"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Security & JWT
    SECRET_KEY: str = "YOUR_SUPER_SECRET_STRONG_KEY_CHANGE_IN_PRODUCTION_MIN_32_BYTES_HEX"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # Database (PostgreSQL with asyncpg)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "doc_classifier"
    DATABASE_URL: str = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    # Sync DB URL for Alembic migrations
    SYNC_DATABASE_URL: str = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # Redis & ARQ Task Queue
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # LLM Inference (llama.cpp server)
    LLAMA_CPP_URL: str = "http://localhost:8080/v1/chat/completions"
    LLAMA_MODEL_NAME: str = "Llama-3.2-3B-Instruct"
    LLM_REQUEST_TIMEOUT_SECONDS: float = 60.0

    # OCR Settings
    PADDLE_OCR_USE_GPU: bool = False
    PADDLE_OCR_LANG: str = "en"

    # File Storage & Limits
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB for large banking dossiers
    ALLOWED_EXTENSIONS: List[str] = [
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tiff",
        ".tif",
        ".bmp",
    ]

    # Security Controls
    CORS_ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    ALLOWED_HOSTS: List[str] = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "testserver",
    ]
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
