"""Application factory for the Horizon WhatsApp bot management service."""
from __future__ import annotations

from flask import Flask

from .config import config_from_env
from .extensions import (
    horizon_extension,
    openai_extension,
    redis_extension,
    twilio_extension,
    db_extension,
)
from .routes import register_blueprints
from .services.horizon_service import HorizonService
from .services.openai_service import OpenAIAssistantService
from .services.twilio_service import TwilioMessagingService


def create_app(config_name: str | None = None) -> Flask:
    """Application factory used by the Flask CLI and WSGI servers."""
    app = Flask(__name__)

    config_object = config_from_env(config_name)
    app.config.from_object(config_object)

    # Initialize core extensions
    redis_extension.init_app(app)
    openai_extension.init_app(app)
    twilio_extension.init_app(app)
    horizon_extension.init_app(app)
    db_extension.init_app(app)

    # Bind higher-level services so they can be injected from the Flask app context
    app.extensions["openai_service"] = OpenAIAssistantService(openai_extension)
    app.extensions["twilio_service"] = TwilioMessagingService(twilio_extension)
    app.extensions["horizon_service"] = HorizonService(horizon_extension)

    register_blueprints(app)

    @app.get("/health")
    def healthcheck() -> tuple[dict[str, str | bool], int]:
        db_ok = False
        try:
            db_ok = db_extension.health_check()
        except Exception:  # pragma: no cover
            db_ok = False
        return {"status": "ok", "db": db_ok}, 200

    @app.get("/debug/routes")
    def list_routes():
        """Debug endpoint to see all registered routes."""
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                "endpoint": rule.endpoint,
                "methods": list(rule.methods),
                "rule": rule.rule
            })
        return {"routes": routes}

    @app.get("/health/db")
    def db_health() -> tuple[dict[str, str], int]:
        try:
            if db_extension.health_check():
                return {"database": "ok"}, 200
            return {"database": "unavailable"}, 503
        except Exception as exc:  # pragma: no cover
            return {"database": "error", "detail": str(exc)}, 500

    @app.get("/debug/routes")
    def debug_routes():
        """Show all registered routes for debugging."""
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                "endpoint": rule.endpoint,
                "methods": list(rule.methods),
                "rule": str(rule)
            })
        return {"routes": routes}

    return app
