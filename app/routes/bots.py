"""Endpoints for managing bot definitions."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any, Dict, Optional

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.exceptions import BadRequest, NotFound

from ..extensions import redis_extension
from ..extensions import db_extension
from ..repositories import BotRepository
from ..services.openai_service import OpenAIAssistantService
from ..utils.validation import ValidationError, require_fields
from ..repositories.sql_bot_repository import SQLBotRepository

blueprint = Blueprint("bots", __name__)


def _get_repository() -> BotRepository:
    return BotRepository(redis_extension.client)


def _get_openai_service() -> OpenAIAssistantService:
    return current_app.extensions["openai_service"]


@blueprint.get("/")
def list_bots() -> Response:
    repository = _get_repository()
    bots = repository.list_bots()
    return jsonify({"data": bots})


@blueprint.post("/")
def create_bot() -> Response:
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        require_fields(payload, ["name", "twilio_phone_number"])
    except ValidationError as exc:
        raise BadRequest(str(exc)) from exc

    assistant_config: Optional[Dict[str, Any]] = payload.get("assistant_config")
    assistant_response: Optional[Dict[str, Any]] = None

    if assistant_config:
        if not assistant_config.get("instructions") and not payload.get("instructions"):
            raise BadRequest(
                "assistant_config.instructions or payload.instructions is required to bootstrap the assistant"
            )
        openai_service = _get_openai_service()
        assistant_response = openai_service.create_assistant(
            name=assistant_config.get("name") or payload["name"],
            instructions=assistant_config.get("instructions") or payload.get("instructions") or "",
            model=assistant_config.get("model"),
            tools=assistant_config.get("tools"),
            metadata=assistant_config.get("metadata"),
        )

    bot_data: Dict[str, Any] = {
        "name": payload["name"],
        "instructions": payload.get("instructions")
        or (assistant_response or {}).get("instructions"),
        "openai_model": payload.get("openai_model")
        or (assistant_response or {}).get("model"),
        "assistant_id": payload.get("assistant_id") or (assistant_response or {}).get("id"),
        "assistant_functions": payload.get("assistant_functions") or [],
        "horizon_actions": payload.get("horizon_actions") or [],
        "metadata": payload.get("metadata") or {},
        "twilio_phone_number": payload.get("twilio_phone_number"),
    }

    repository = _get_repository()
    created_bot = repository.create_bot(bot_data)

    response_body: Dict[str, Any] = {"data": created_bot}
    if assistant_response:
        response_body["assistant"] = assistant_response
    return jsonify(response_body), HTTPStatus.CREATED


@blueprint.get("/<bot_id>")
def get_bot(bot_id: str) -> Response:
    repository = _get_repository()
    bot = repository.get_bot(bot_id)
    if not bot:
        raise NotFound(f"Bot '{bot_id}' not found")
    return jsonify({"data": bot})


@blueprint.put("/<bot_id>")
def update_bot(bot_id: str) -> Response:
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    repository = _get_repository()
    current = repository.get_bot(bot_id)
    if not current:
        raise NotFound(f"Bot '{bot_id}' not found")

    assistant_updates: Optional[Dict[str, Any]] = payload.get("assistant_updates")
    assistant_response: Optional[Dict[str, Any]] = None

    if assistant_updates:
        openai_service = _get_openai_service()
        assistant_id = assistant_updates.get("assistant_id") or payload.get("assistant_id") or current.get(
            "assistant_id"
        )
        if not assistant_id:
            raise BadRequest("assistant_id is required to update the assistant")
        assistant_response = openai_service.update_assistant(assistant_id, **assistant_updates)
        payload.setdefault("assistant_id", assistant_response.get("id"))
        payload.setdefault("openai_model", assistant_response.get("model"))
        payload.setdefault("instructions", assistant_response.get("instructions"))

    updated_bot = repository.update_bot(bot_id, payload)
    response_body: Dict[str, Any] = {"data": updated_bot}
    if assistant_response:
        response_body["assistant"] = assistant_response
    return jsonify(response_body)


@blueprint.delete("/<bot_id>")
def delete_bot(bot_id: str) -> Response:
    repository = _get_repository()
    deleted = repository.delete_bot(bot_id)
    if not deleted:
        raise NotFound(f"Bot '{bot_id}' not found")
    return Response(status=HTTPStatus.NO_CONTENT)


@blueprint.post("/<bot_id>/refresh")
def refresh_bot(bot_id: str) -> Response:
    """Force refresh a bot definition from the SQL database into Redis cache."""
    repository = _get_repository()
    try:
        engine = db_extension.engine
    except Exception:  # pragma: no cover
        raise BadRequest("Database not configured")

    sql_repo = SQLBotRepository(engine)
    record = sql_repo.get(bot_id)
    if not record:
        raise NotFound(f"Bot '{bot_id}' not found in database")

    # Upsert minimal snapshot in Redis
    snapshot = {
        "id": record.get("id"),
        "name": record.get("external_ref") or record.get("id"),
        "instructions": record.get("assistant_instructions"),
        "assistant_id": record.get("assistant_id"),
        "openai_model": record.get("assistant_model"),
        "assistant_functions": record.get("assistant_functions") or [],
        "horizon_actions": record.get("horizon_actions") or [],
        "twilio_phone_number": record.get("twilio_phone_number"),
        "metadata": record.get("metadata") or {},
    }
    repository.create_bot(snapshot)
    return jsonify({"data": snapshot, "source": "database"}), 200
