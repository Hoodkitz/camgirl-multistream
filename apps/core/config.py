"""Core configuration."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/camgirl")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    STREAMING_PORT: int = int(os.getenv("STREAMING_PORT", "8000"))

    class Config:
        env_file = ".env"


settings = Settings()
