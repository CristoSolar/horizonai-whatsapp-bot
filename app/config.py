"""Configuration objects and helpers for the Flask application."""
from __future__ import annotations

import os
from typing import Type


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    JSON_SORT_KEYS = False

    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_SESSION_TTL_SECONDS = int(os.getenv("REDIS_SESSION_TTL_SECONDS", "86400"))

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4.1-mini")
    OPENAI_DEFAULT_INSTRUCTIONS = os.getenv(
        "OPENAI_DEFAULT_INSTRUCTIONS",
        "You are a WhatsApp support assistant. Provide concise, helpful answers in Spanish by default.",
    )

    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

    HORIZON_API_KEY = os.getenv("HORIZON_API_KEY")
    HORIZON_BASE_URL = os.getenv("HORIZON_BASE_URL", "https://api.horizon.local")

    # Database (Horizon persistence / dynamic credentials store)
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    DB_SSL_MODE = os.getenv("DB_SSL_MODE", "prefer")
    DATABASE_URL = os.getenv("DATABASE_URL")

    @property
    def SQLALCHEMY_URL(self):  # type: ignore
        if self.DATABASE_URL:
            return self.DATABASE_URL
        # build if not provided explicitly
        if self.DB_HOST and self.DB_USER and self.DB_NAME:
            return (
                f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@"
                f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?sslmode={self.DB_SSL_MODE}"
            )
        return None
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DB_HOST and self.DB_USER and self.DB_NAME:
            return (
                f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@"
                f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?sslmode={self.DB_SSL_MODE}"
            )
        return None

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    USE_FAKE_REDIS = True
    REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


class ProductionConfig(BaseConfig):
    DEBUG = False


_CONFIG_MAP: dict[str, Type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def config_from_env(config_name: str | None) -> Type[BaseConfig]:
    """Return an appropriate config object based on environment input."""
    env_name = (config_name or os.getenv("FLASK_ENV", "development")).lower()
    return _CONFIG_MAP.get(env_name, DevelopmentConfig)
