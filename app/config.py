"""Configuration management using environment variables."""

import os
from typing import Optional


class Config:
    """Application configuration from environment variables."""

    WEBHOOK_SECRET: Optional[str] = os.getenv("WEBHOOK_SECRET")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    @classmethod
    def validate(cls) -> bool:
        """Validate critical configuration."""
        if not cls.WEBHOOK_SECRET or len(cls.WEBHOOK_SECRET.strip()) == 0:
            return False
        return True


config = Config()
