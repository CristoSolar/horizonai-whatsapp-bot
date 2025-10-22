"""Application extensions and service clients."""
from __future__ import annotations

import logging
from typing import Optional

import redis
from flask import Flask

try:  # Optional dependencies for type checking
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - handled in runtime
    OpenAI = None  # type: ignore

try:
    from twilio.rest import Client as TwilioClient  # type: ignore
except ImportError:  # pragma: no cover - handled in runtime
    TwilioClient = None  # type: ignore

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class RedisExtension:
    """Configure a Redis client for the application."""

    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None

    def init_app(self, app: Flask) -> None:
        if self._client is not None:
            return

        redis_url = app.config.get("REDIS_URL")
        use_fake = app.config.get("USE_FAKE_REDIS")
        decode_responses = True

        if use_fake:
            try:
                import fakeredis  # type: ignore

                self._client = fakeredis.FakeRedis(decode_responses=decode_responses)
                logger.info("Initialized FakeRedis for testing use case")
            except ImportError:  # pragma: no cover - executed only when fakeredis missing
                logger.warning("fakeredis not installed; falling back to real Redis client")

        if self._client is None:
            if not redis_url:
                raise RuntimeError("REDIS_URL is required when fakeredis is not available")
            self._client = redis.Redis.from_url(redis_url, decode_responses=decode_responses)
            logger.info("Connected to Redis at %s", redis_url)

        app.extensions["redis_extension"] = self

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        return self._client


class OpenAIExtension:
    """Configure access to OpenAI assistants API."""

    def __init__(self) -> None:
        self._client: Optional[OpenAI] = None

    def init_app(self, app: Flask) -> None:
        if self._client is not None:
            return

        api_key = app.config.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not configured; assistant features disabled")
            app.extensions["openai_extension"] = self
            return

        if OpenAI is None:
            raise RuntimeError(
                "openai package not installed. Please add 'openai' to requirements.txt"
            )

        # Initialize OpenAI client with explicit HTTP client configuration
        try:
            import httpx
            # Create HTTP client without proxy configuration
            http_client = httpx.Client(
                timeout=60.0,
                limits=httpx.Limits(max_keepalive_connections=1, max_connections=10)
            )
            self._client = OpenAI(api_key=api_key, http_client=http_client)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"OpenAI client initialization failed: {e}")
            # Try fallback initialization
            try:
                self._client = OpenAI(api_key=api_key, max_retries=0)
                logger.info("OpenAI client initialized with fallback configuration")
            except Exception as e2:
                logger.error(f"OpenAI fallback initialization also failed: {e2}")
                self._client = None
        app.extensions["openai_extension"] = self
        logger.info("OpenAI client initialized")

    @property
    def client(self) -> Optional[OpenAI]:
        return self._client


class TwilioExtension:
    """Configure Twilio REST client."""

    def __init__(self) -> None:
        self._client: Optional[TwilioClient] = None

    def init_app(self, app: Flask) -> None:
        if self._client is not None:
            return

        account_sid = app.config.get("TWILIO_ACCOUNT_SID")
        auth_token = app.config.get("TWILIO_AUTH_TOKEN")

        if not account_sid or not auth_token:
            logger.warning("Twilio credentials missing; outbound WhatsApp messages disabled")
            app.extensions["twilio_extension"] = self
            return

        if TwilioClient is None:
            raise RuntimeError(
                "twilio package not installed. Please add 'twilio' to requirements.txt"
            )

        self._client = TwilioClient(account_sid, auth_token)
        app.extensions["twilio_extension"] = self
        logger.info("Twilio client initialized")

    @property
    def client(self) -> Optional[TwilioClient]:
        return self._client


class HorizonExtension:
    """HTTP session wrapper to communicate with Horizon's API."""

    def __init__(self) -> None:
        self._session: Optional[requests.Session] = None
        self._base_url: Optional[str] = None

    def init_app(self, app: Flask) -> None:
        if self._session is not None:
            return

        base_url = app.config.get("HORIZON_BASE_URL")
        api_key = app.config.get("HORIZON_API_KEY")

        session = requests.Session()
        if api_key:
            session.headers.update({"Authorization": f"Bearer {api_key}"})
        session.headers.update({"Content-Type": "application/json"})

        self._session = session
        self._base_url = base_url
        app.extensions["horizon_extension"] = self
        logger.info("Horizon client configured with base URL %s", base_url)

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            raise RuntimeError("Horizon session not initialized")
        return self._session

    @property
    def base_url(self) -> str:
        if not self._base_url:
            raise RuntimeError("Horizon base URL not configured")
        return self._base_url


class DatabaseExtension:
    """Lightweight SQLAlchemy engine wrapper for Horizon DB access."""

    def __init__(self) -> None:
        self._engine: Optional[Engine] = None

    def init_app(self, app: Flask) -> None:
        if self._engine is not None:
            return
        # Determine URL
        config_obj = app.config
        url = None
        # Support config object property
        if hasattr(config_obj, "SQLALCHEMY_URL"):
            try:
                url = config_obj.SQLALCHEMY_URL  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                url = None
        url = url or config_obj.get("DATABASE_URL")
        if not url:
            logger.warning("DATABASE_URL not configured; DB features disabled")
            app.extensions["db_extension"] = self
            return
        self._engine = create_engine(url, pool_pre_ping=True, future=True)
        app.extensions["db_extension"] = self
        logger.info("Database engine initialized")

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Database engine not initialized")
        return self._engine

    def health_check(self) -> bool:
        if self._engine is None:
            return False
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:  # pragma: no cover
            return False


redis_extension = RedisExtension()
openai_extension = OpenAIExtension()
twilio_extension = TwilioExtension()
horizon_extension = HorizonExtension()
db_extension = DatabaseExtension()
