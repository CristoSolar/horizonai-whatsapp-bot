"""Outbound WhatsApp delivery helpers for Horizon Flow integration."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Dict, Optional

try:
    from twilio.base.exceptions import TwilioRestException  # type: ignore
    from twilio.rest import Client as TwilioClient  # type: ignore
except Exception:  # pragma: no cover
    TwilioRestException = Exception  # type: ignore
    TwilioClient = None  # type: ignore


LAST_INBOUND_KEY = "wa:last_inbound:{tenant_id}:{to_e164}"
OUTBOUND_MESSAGE_KEY = "wa:outbound:message:{message_sid}"
OUTBOUND_STATUS_KEY = "wa:outbound:status:{message_sid}"
IDEMPOTENCY_KEY = "wa:outbound:idempotency:{tenant_id}:{idempotency_key}"


@dataclass
class OutboundResult:
    status: str
    twilio_message_sid: Optional[str]
    client_message_id: Optional[str]
    provider_status: Optional[str]
    reason_code: Optional[str]
    reason_message: Optional[str]
    window_open: bool
    conversation_expires_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "twilio_message_sid": self.twilio_message_sid,
            "client_message_id": self.client_message_id,
            "provider_status": self.provider_status,
            "reason_code": self.reason_code,
            "reason_message": self.reason_message,
            "window_open": self.window_open,
            "conversation_expires_at": self.conversation_expires_at,
        }


class OutboundWhatsAppService:
    @staticmethod
    def _to_utc_iso_z(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def __init__(self, redis_client, *, status_callback_url: Optional[str] = None) -> None:
        self._redis = redis_client
        self._status_callback_url = status_callback_url

    @staticmethod
    def normalize_e164(number: str) -> str:
        value = (number or "").strip().replace("whatsapp:", "")
        return value

    @staticmethod
    def whatsapp_number(number: str) -> str:
        clean = OutboundWhatsAppService.normalize_e164(number)
        return clean if clean.startswith("whatsapp:") else f"whatsapp:{clean}"

    def mark_last_inbound(self, *, tenant_id: str, to_e164: str, at: Optional[datetime] = None) -> None:
        now = at or datetime.now(UTC)
        key = LAST_INBOUND_KEY.format(
            tenant_id=tenant_id,
            to_e164=self.normalize_e164(to_e164),
        )
        self._redis.set(key, str(int(now.timestamp())))

    def get_window_state(self, *, tenant_id: str, to_e164: str) -> tuple[bool, Optional[str]]:
        key = LAST_INBOUND_KEY.format(
            tenant_id=tenant_id,
            to_e164=self.normalize_e164(to_e164),
        )
        raw_value = self._redis.get(key)
        if not raw_value:
            return False, None
        try:
            inbound_epoch = int(raw_value)
        except (ValueError, TypeError):
            return False, None
        inbound_at = datetime.fromtimestamp(inbound_epoch, tz=UTC)
        expires_at = inbound_at + timedelta(hours=24)
        now = datetime.now(UTC)
        return now <= expires_at, self._to_utc_iso_z(expires_at)

    def get_idempotency_record(self, *, tenant_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        key = IDEMPOTENCY_KEY.format(tenant_id=tenant_id, idempotency_key=idempotency_key)
        payload = self._redis.get(key)
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def save_idempotency_record(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_body: bytes,
        response: Dict[str, Any],
        status_code: int,
        ttl_seconds: int = 172800,
    ) -> None:
        key = IDEMPOTENCY_KEY.format(tenant_id=tenant_id, idempotency_key=idempotency_key)
        record = {
            "request_hash": sha256(request_body).hexdigest(),
            "response": response,
            "status_code": status_code,
        }
        self._redis.setex(key, ttl_seconds, json.dumps(record))

    @staticmethod
    def request_hash(raw_body: bytes) -> str:
        return sha256(raw_body).hexdigest()

    def send(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        execution_id: str,
        client_message_id: Optional[str],
        to_e164: str,
        twilio_account_sid: str,
        twilio_auth_token: str,
        twilio_from_whatsapp: str,
        mode: str,
        text: Optional[str] = None,
        template_sid: Optional[str] = None,
        template_vars: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> OutboundResult:
        window_open, expires_at = self.get_window_state(tenant_id=tenant_id, to_e164=to_e164)

        if mode == "free" and not window_open:
            return OutboundResult(
                status="blocked_window_closed",
                twilio_message_sid=None,
                client_message_id=client_message_id,
                provider_status=None,
                reason_code="requires_template",
                reason_message="Window closed. Use template mode to re-open conversation.",
                window_open=False,
                conversation_expires_at=expires_at,
            )

        if TwilioClient is None:
            return OutboundResult(
                status="error",
                twilio_message_sid=None,
                client_message_id=client_message_id,
                provider_status=None,
                reason_code="twilio_client_unavailable",
                reason_message="Twilio SDK is not available in runtime.",
                window_open=window_open,
                conversation_expires_at=expires_at,
            )

        try:
            client = TwilioClient(twilio_account_sid, twilio_auth_token)
            to_number = self.whatsapp_number(to_e164)
            from_number = self.whatsapp_number(twilio_from_whatsapp)

            create_params: Dict[str, Any] = {
                "to": to_number,
                "from_": from_number,
            }
            if self._status_callback_url:
                create_params["status_callback"] = self._status_callback_url

            if mode == "template":
                create_params["content_sid"] = template_sid
                create_params["content_variables"] = json.dumps(template_vars or {})
            else:
                create_params["body"] = text or ""

            message = client.messages.create(**create_params)
            sid = getattr(message, "sid", None)
            provider_status = getattr(message, "status", None)

            if sid:
                self._redis.setex(
                    OUTBOUND_MESSAGE_KEY.format(message_sid=sid),
                    172800,
                    json.dumps(
                        {
                            "tenant_id": tenant_id,
                            "lead_id": lead_id,
                            "execution_id": execution_id,
                            "client_message_id": client_message_id,
                            "idempotency_key": idempotency_key,
                            "to_e164": self.normalize_e164(to_e164),
                            "mode": mode,
                            "created_at": self._to_utc_iso_z(datetime.now(UTC)),
                        }
                    ),
                )

            return OutboundResult(
                status="sent_template" if mode == "template" else "sent_free",
                twilio_message_sid=sid,
                client_message_id=client_message_id,
                provider_status=provider_status,
                reason_code=None,
                reason_message=None,
                window_open=window_open,
                conversation_expires_at=expires_at,
            )
        except TwilioRestException as exc:
            code = getattr(exc, "code", None)
            status_code = getattr(exc, "status", None)
            reason = str(exc)
            reason_code = "invalid_credentials" if status_code == 401 else "twilio_error"
            if code:
                reason_code = f"{reason_code}_{code}"
            return OutboundResult(
                status="error",
                twilio_message_sid=None,
                client_message_id=client_message_id,
                provider_status=None,
                reason_code=reason_code,
                reason_message=reason,
                window_open=window_open,
                conversation_expires_at=expires_at,
            )
        except Exception as exc:
            return OutboundResult(
                status="error",
                twilio_message_sid=None,
                client_message_id=client_message_id,
                provider_status=None,
                reason_code="internal_error",
                reason_message=str(exc),
                window_open=window_open,
                conversation_expires_at=expires_at,
            )

    def process_status_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message_sid = payload.get("MessageSid") or payload.get("SmsSid")
        provider_status = payload.get("MessageStatus") or payload.get("SmsStatus")
        error_code = payload.get("ErrorCode")
        error_message = payload.get("ErrorMessage")

        correlation: Dict[str, Any] = {}
        if message_sid:
            raw = self._redis.get(OUTBOUND_MESSAGE_KEY.format(message_sid=message_sid))
            if raw:
                try:
                    correlation = json.loads(raw)
                except json.JSONDecodeError:
                    correlation = {}

            self._redis.setex(
                OUTBOUND_STATUS_KEY.format(message_sid=message_sid),
                172800,
                json.dumps(
                    {
                        "message_sid": message_sid,
                        "provider_status": provider_status,
                        "error_code": error_code,
                        "error_message": error_message,
                        "updated_at": self._to_utc_iso_z(datetime.now(UTC)),
                        "correlation": correlation,
                    }
                ),
            )

        return {
            "status": "received",
            "twilio_message_sid": message_sid,
            "client_message_id": correlation.get("client_message_id"),
            "provider_status": provider_status,
            "execution_id": correlation.get("execution_id"),
            "tenant_id": correlation.get("tenant_id"),
            "error_code": error_code,
            "error_message": error_message,
        }
