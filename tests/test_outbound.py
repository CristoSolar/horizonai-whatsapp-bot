from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from app import create_app
from app.extensions import redis_extension
from app.services.outbound_whatsapp_service import OutboundWhatsAppService
import app.services.outbound_whatsapp_service as outbound_module


class _FakeMessage:
    def __init__(self, sid: str = "SM123", status: str = "queued") -> None:
        self.sid = sid
        self.status = status


class _FakeMessagesApi:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.should_fail:
            raise FakeTwilioAuthError("Authentication Error", status=401, code=20003)
        return _FakeMessage()


class _FakeTwilioClient:
    def __init__(self, account_sid: str, auth_token: str, should_fail: bool = False) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.messages = _FakeMessagesApi(should_fail=should_fail)


class FakeTwilioAuthError(Exception):
    def __init__(self, message: str, *, status: int = 401, code: int = 20003) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _signed_request(
    client,
    path: str,
    payload: dict,
    *,
    api_key: str,
    hmac_secret: str,
    timestamp: str | None = None,
):
    raw = json.dumps(payload, separators=(",", ":"))
    request_timestamp = timestamp or datetime.now(UTC).isoformat()
    signature = hmac.new(
        hmac_secret.encode("utf-8"),
        f"{request_timestamp}.{raw}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return client.post(
        path,
        data=raw,
        content_type="application/json",
        headers={
            "X-Api-Key": api_key,
            "X-Timestamp": request_timestamp,
            "X-Signature": signature,
        },
    )


@pytest.fixture()
def app(monkeypatch):
    app = create_app("testing")
    app.config["OUTBOUND_API_KEY"] = "svc-key"
    app.config["OUTBOUND_HMAC_SECRET"] = "svc-secret"
    app.config["TWILIO_AUTH_TOKEN_REFS"] = {"ref_main": "token-123"}

    monkeypatch.setattr(outbound_module, "TwilioRestException", FakeTwilioAuthError)
    monkeypatch.setattr(outbound_module, "TwilioClient", lambda sid, token: _FakeTwilioClient(sid, token))

    yield app
    redis_extension.client.flushdb()


@pytest.fixture()
def client(app):
    return app.test_client()


def _base_payload(**overrides):
    payload = {
        "tenant_id": "tenant-a",
        "lead_id": "lead-1",
        "execution_id": "exec-1",
        "to_e164": "+56911111111",
        "twilio_account_sid": "AC123",
        "twilio_auth_token_ref": "ref_main",
        "twilio_from_whatsapp": "+56922222222",
        "mode": "free",
        "text": "Hola desde flow",
        "idempotency_key": "idem-1",
    }
    payload.update(overrides)
    return payload


def test_outbound_free_window_open(client):
    service = OutboundWhatsAppService(redis_extension.client)
    service.mark_last_inbound(tenant_id="tenant-a", to_e164="+56911111111")

    response = _signed_request(
        client,
        "/outbound/whatsapp/send",
        _base_payload(),
        api_key="svc-key",
        hmac_secret="svc-secret",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "sent_free"
    assert body["window_open"] is True
    assert body["twilio_message_sid"] == "SM123"


def test_outbound_free_window_closed(client):
    past = datetime.now(UTC) - timedelta(hours=25)
    service = OutboundWhatsAppService(redis_extension.client)
    service.mark_last_inbound(tenant_id="tenant-a", to_e164="+56911111111", at=past)

    response = _signed_request(
        client,
        "/outbound/whatsapp/send",
        _base_payload(idempotency_key="idem-2"),
        api_key="svc-key",
        hmac_secret="svc-secret",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "blocked_window_closed"
    assert body["reason_code"] == "requires_template"
    assert body["window_open"] is False


def test_outbound_template_ok(client):
    payload = _base_payload(
        mode="template",
        text=None,
        template_sid="HX123",
        template_vars={"1": "Cristobal"},
        idempotency_key="idem-3",
    )

    response = _signed_request(
        client,
        "/outbound/whatsapp/send",
        payload,
        api_key="svc-key",
        hmac_secret="svc-secret",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "sent_template"
    assert body["twilio_message_sid"] == "SM123"


def test_outbound_client_message_id_echo(client):
    service = OutboundWhatsAppService(redis_extension.client)
    service.mark_last_inbound(tenant_id="tenant-a", to_e164="+56911111111")

    payload = _base_payload(
        idempotency_key="idem-client-msg-1",
        client_message_id="5f786a58-b45d-4128-a56f-f0b9f65c8dcf",
    )

    response = _signed_request(
        client,
        "/outbound/whatsapp/send",
        payload,
        api_key="svc-key",
        hmac_secret="svc-secret",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["client_message_id"] == "5f786a58-b45d-4128-a56f-f0b9f65c8dcf"


def test_outbound_invalid_signature_reason_code(client):
    payload = _base_payload(idempotency_key="idem-invalid-signature")
    raw = json.dumps(payload, separators=(",", ":"))
    timestamp = datetime.now(UTC).isoformat()
    response = client.post(
        "/outbound/whatsapp/send",
        data=raw,
        content_type="application/json",
        headers={
            "X-Api-Key": "svc-key",
            "X-Timestamp": timestamp,
            "X-Signature": "bad-signature",
        },
    )

    assert response.status_code == 401
    body = response.get_json()
    assert body["reason_code"] == "invalid_signature"


def test_outbound_invalid_credentials(client, monkeypatch):
    monkeypatch.setattr(
        outbound_module,
        "TwilioClient",
        lambda sid, token: _FakeTwilioClient(sid, token, should_fail=True),
    )

    service = OutboundWhatsAppService(redis_extension.client)
    service.mark_last_inbound(tenant_id="tenant-a", to_e164="+56911111111")

    response = _signed_request(
        client,
        "/outbound/whatsapp/send",
        _base_payload(idempotency_key="idem-4"),
        api_key="svc-key",
        hmac_secret="svc-secret",
    )

    assert response.status_code == 502
    body = response.get_json()
    assert body["status"] == "error"
    assert body["reason_code"].startswith("invalid_credentials")


def test_outbound_idempotency_repeat(client):
    service = OutboundWhatsAppService(redis_extension.client)
    service.mark_last_inbound(tenant_id="tenant-a", to_e164="+56911111111")

    payload = _base_payload(idempotency_key="idem-5")
    ts1 = datetime.now(UTC).isoformat()
    ts2 = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    first = _signed_request(
        client,
        "/outbound/whatsapp/send",
        payload,
        api_key="svc-key",
        hmac_secret="svc-secret",
        timestamp=ts1,
    )
    second = _signed_request(
        client,
        "/outbound/whatsapp/send",
        payload,
        api_key="svc-key",
        hmac_secret="svc-secret",
        timestamp=ts2,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json() == second.get_json()
