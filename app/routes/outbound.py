"""Outbound endpoints for Horizon Flow to send WhatsApp messages."""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.exceptions import BadRequest, Unauthorized

from ..extensions import redis_extension
from ..services.outbound_whatsapp_service import OutboundWhatsAppService

blueprint = Blueprint("outbound", __name__)
logger = logging.getLogger(__name__)


def _service() -> OutboundWhatsAppService:
    callback_url = current_app.config.get("OUTBOUND_STATUS_CALLBACK_URL")
    return OutboundWhatsAppService(redis_extension.client, status_callback_url=callback_url)


def _parse_timestamp(raw_value: str) -> datetime:
    value = (raw_value or "").strip()
    if not value:
        raise BadRequest("Missing X-Timestamp header")
    if value.isdigit():
        return datetime.fromtimestamp(int(value), tz=UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise BadRequest("Invalid X-Timestamp format") from exc


def _verify_service_auth(raw_body: bytes) -> None:
    api_key = request.headers.get("X-Api-Key")
    signature_header = request.headers.get("X-Signature")
    timestamp_header = request.headers.get("X-Timestamp")

    expected_api_key = current_app.config.get("OUTBOUND_API_KEY")
    hmac_secret = current_app.config.get("OUTBOUND_HMAC_SECRET")
    max_skew = int(current_app.config.get("OUTBOUND_MAX_TIMESTAMP_SKEW_SECONDS", 300))

    if not expected_api_key or not hmac_secret:
        raise Unauthorized("service_auth_not_configured")

    if not api_key or not hmac.compare_digest(api_key, expected_api_key):
        raise Unauthorized("invalid_api_key")
    if not signature_header:
        raise Unauthorized("missing_signature")

    req_ts = _parse_timestamp(timestamp_header or "")
    now = datetime.now(UTC)
    skew = abs((now - req_ts).total_seconds())
    if skew > max_skew:
        raise Unauthorized("timestamp_out_of_skew")

    signed_payload = f"{timestamp_header}.{raw_body.decode('utf-8')}".encode("utf-8")
    computed = hmac.new(
        hmac_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    presented = signature_header.replace("sha256=", "")
    if not hmac.compare_digest(presented, computed):
        raise Unauthorized("invalid_signature")

    replay_key = f"auth:replay:{timestamp_header}:{presented}"
    if not redis_extension.client.set(replay_key, "1", nx=True, ex=max_skew):
        raise Unauthorized("replay_detected")


def _error_response(*, reason_code: str, reason_message: str, http_status: int) -> tuple[Response, int]:
    body = {
        "status": "error",
        "twilio_message_sid": None,
        "client_message_id": None,
        "provider_status": None,
        "reason_code": reason_code,
        "reason_message": reason_message,
        "window_open": False,
        "conversation_expires_at": None,
    }
    return jsonify(body), http_status


def _resolve_twilio_auth_token(payload: Dict[str, Any]) -> Optional[str]:
    token_ref = payload.get("twilio_auth_token_ref")
    if token_ref:
        token_map = current_app.config.get("TWILIO_AUTH_TOKEN_REFS") or {}
        token = token_map.get(token_ref)
        if token:
            return token

    tenant_id = payload.get("tenant_id")
    if tenant_id:
        tenant_key = f"tenant:twilio:{tenant_id}"
        token = redis_extension.client.hget(tenant_key, "twilio_auth_token")
        if token:
            return token
    return None


def _resolve_field(payload: Dict[str, Any], field_name: str) -> Optional[str]:
    value = payload.get(field_name)
    if value:
        return value
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        return None
    tenant_key = f"tenant:twilio:{tenant_id}"
    fallback = redis_extension.client.hget(tenant_key, field_name)
    return fallback or None


def _validate_payload(payload: Dict[str, Any]) -> None:
    required = [
        "tenant_id",
        "lead_id",
        "execution_id",
        "to_e164",
        "mode",
        "idempotency_key",
    ]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise BadRequest(f"Missing required fields: {', '.join(missing)}")

    mode = payload.get("mode")
    if mode not in {"free", "template"}:
        raise BadRequest("mode must be either 'free' or 'template'")

    if mode == "free" and not payload.get("text"):
        raise BadRequest("text is required when mode=free")
    if mode == "template" and not payload.get("template_sid"):
        raise BadRequest("template_sid is required when mode=template")


@blueprint.post("/outbound/whatsapp/send")
def outbound_send() -> Response:
    raw_body = request.get_data(cache=True) or b"{}"
    try:
        _verify_service_auth(raw_body)
    except Unauthorized as exc:
        code = getattr(exc, "description", "unauthorized") or "unauthorized"
        return _error_response(reason_code=str(code), reason_message="Unauthorized request", http_status=401)
    except BadRequest as exc:
        code = "invalid_timestamp"
        return _error_response(reason_code=code, reason_message=str(exc.description), http_status=400)

    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        _validate_payload(payload)
    except BadRequest as exc:
        return _error_response(reason_code="invalid_payload", reason_message=str(exc.description), http_status=400)

    tenant_id = payload["tenant_id"]
    idempotency_key = payload["idempotency_key"]

    service = _service()
    existing = service.get_idempotency_record(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    current_hash = service.request_hash(raw_body)

    if existing:
        if existing.get("request_hash") != current_hash:
            conflict = {
                "status": "error",
                "twilio_message_sid": None,
                "client_message_id": payload.get("client_message_id"),
                "provider_status": None,
                "reason_code": "idempotency_conflict",
                "reason_message": "idempotency_key already used with a different request payload",
                "window_open": False,
                "conversation_expires_at": None,
            }
            return jsonify(conflict), 409
        stored_response = existing.get("response") or {}
        stored_status = int(existing.get("status_code") or 200)
        return jsonify(stored_response), stored_status

    twilio_account_sid = _resolve_field(payload, "twilio_account_sid")
    twilio_from_whatsapp = _resolve_field(payload, "twilio_from_whatsapp")
    twilio_auth_token = _resolve_twilio_auth_token(payload)

    if not twilio_account_sid or not twilio_from_whatsapp or not twilio_auth_token:
        response = {
            "status": "error",
            "twilio_message_sid": None,
            "client_message_id": payload.get("client_message_id"),
            "provider_status": None,
            "reason_code": "missing_credentials",
            "reason_message": "Twilio credentials are incomplete for this tenant/request",
            "window_open": False,
            "conversation_expires_at": None,
        }
        service.save_idempotency_record(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_body=raw_body,
            response=response,
            status_code=400,
        )
        return jsonify(response), 400

    result = service.send(
        tenant_id=tenant_id,
        lead_id=str(payload["lead_id"]),
        execution_id=str(payload["execution_id"]),
        client_message_id=payload.get("client_message_id"),
        to_e164=str(payload["to_e164"]),
        twilio_account_sid=twilio_account_sid,
        twilio_auth_token=twilio_auth_token,
        twilio_from_whatsapp=twilio_from_whatsapp,
        mode=str(payload["mode"]),
        text=payload.get("text"),
        template_sid=payload.get("template_sid"),
        template_vars=payload.get("template_vars") or {},
        idempotency_key=idempotency_key,
    )
    response = result.to_dict()
    status_code = 200 if result.status in {"sent_free", "sent_template", "blocked_window_closed"} else 502

    service.save_idempotency_record(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        request_body=raw_body,
        response=response,
        status_code=status_code,
    )

    logger.info(
        "Outbound send processed tenant=%s execution_id=%s status=%s",
        tenant_id,
        payload.get("execution_id"),
        result.status,
    )
    return jsonify(response), status_code


@blueprint.post("/outbound/whatsapp/status")
def outbound_status_webhook() -> Response:
    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    service = _service()
    response = service.process_status_webhook(payload)

    logger.info(
        "Outbound status received sid=%s provider_status=%s execution_id=%s",
        response.get("twilio_message_sid"),
        response.get("provider_status"),
        response.get("execution_id"),
    )
    return jsonify(response), 200
