"""Tests for the CRM human-handoff check (control-status)."""
from __future__ import annotations

import pytest

from app import create_app
from app.services import conversation_service as cs


@pytest.fixture()
def app():
    app = create_app("testing")
    app.config["HORIZON_CONTROL_BASE_URL"] = "https://crm.test"
    app.config["HORIZON_API_KEY"] = "test-token"
    yield app


BOT = {"id": "b1", "metadata": {"horizon_api_token": "test-token"}}


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_human_control_blocks(app, monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured.update(url=url, params=params, auth=headers["Authorization"])
        return _Resp(200, {"control_mode": "human"})

    monkeypatch.setattr(cs.requests, "get", fake_get)
    with app.app_context():
        assert cs.human_agent_has_control(BOT, "+56912345678") is True
    # Sends the real E.164 sender number and the bearer token.
    assert captured["params"] == {"telefono": "+56912345678"}
    assert captured["auth"] == "Bearer test-token"
    assert captured["url"] == "https://crm.test/api/bot/control-status/"


def test_bot_mode_allows_reply(app, monkeypatch):
    monkeypatch.setattr(cs.requests, "get", lambda *a, **k: _Resp(200, {"control_mode": "bot"}))
    with app.app_context():
        assert cs.human_agent_has_control(BOT, "+56912345678") is False


def test_error_fails_open_after_retry(app, monkeypatch):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        raise cs.requests.RequestException("boom")

    monkeypatch.setattr(cs.requests, "get", fake_get)
    with app.app_context():
        # Fail-open: bot still replies (returns False) but only after one retry.
        assert cs.human_agent_has_control(BOT, "+56912345678") is False
    assert calls["n"] == 2


def test_http_error_fails_open(app, monkeypatch):
    monkeypatch.setattr(cs.requests, "get", lambda *a, **k: _Resp(500, None))
    with app.app_context():
        assert cs.human_agent_has_control(BOT, "+56912345678") is False
