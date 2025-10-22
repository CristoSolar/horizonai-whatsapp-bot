from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app import create_app
from app.extensions import redis_extension
from app.repositories import BotRepository
from app.services.openai_service import AssistantFunctionCall, AssistantResponse


@dataclass
class DummyHorizonService:
    last_action: str | None = None
    last_arguments: dict | None = None

    def execute_action(self, *, action_name: str, defined_actions, arguments: dict) -> dict:
        self.last_action = action_name
        self.last_arguments = arguments
        return {"action": action_name, "arguments": arguments}


class DummyOpenAIService:
    def __init__(self) -> None:
        self.created_assistants: list[dict] = []
        self.reply: AssistantResponse = AssistantResponse(
            reply_text="Hola, ¿en qué puedo ayudarte?", function_calls=[]
        )
        self.summary_text = "He completado la acción"

    def create_assistant(self, **payload):
        payload.setdefault("id", "asst_dummy")
        payload.setdefault("model", "gpt-4.1-mini")
        payload.setdefault("instructions", payload.get("instructions", ""))
        self.created_assistants.append(payload)
        return payload

    def update_assistant(self, assistant_id, **payload):
        payload.setdefault("id", assistant_id)
        payload.setdefault("model", "gpt-4.1-mini")
        return payload

    def generate_reply(self, **kwargs):
        return self.reply

    def summarize_tool_results(self, **kwargs):
        return self.summary_text


@pytest.fixture()
def app():
    app = create_app("testing")
    app.extensions["openai_service"] = DummyOpenAIService()
    app.extensions["horizon_service"] = DummyHorizonService()
    yield app
    redis_extension.client.flushdb()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_create_bot_with_assistant_config(client, app):
    payload = {
        "name": "Soporte",
        "twilio_phone_number": "whatsapp:+111111111",
        "assistant_config": {"instructions": "Ayuda a los usuarios", "model": "gpt-4.1-mini"},
    }

    response = client.post("/bots/", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["data"]["assistant_id"] == "asst_dummy"
    assert data["data"]["name"] == "Soporte"
    assert data["assistant"]["id"] == "asst_dummy"


def test_webhook_returns_twiml(client, app):
    repository = BotRepository(redis_extension.client)
    bot = repository.create_bot(
        {
            "name": "Ventas",
            "assistant_id": "asst_dummy",
            "twilio_phone_number": "whatsapp:+222222222",
            "horizon_actions": [],
        }
    )

    response = client.post(
        "/webhook/whatsapp",
        data={"From": "whatsapp:+549111111", "To": bot["twilio_phone_number"], "Body": "Hola"},
    )

    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert "Hola" in response.get_data(as_text=True)


def test_horizon_function_invocation(client, app):
    repository = BotRepository(redis_extension.client)
    bot = repository.create_bot(
        {
            "name": "Consultas",
            "assistant_id": "asst_dummy",
            "twilio_phone_number": "whatsapp:+333333333",
            "horizon_actions": [
                {"name": "lookup_customer", "method": "GET", "path": "/customers/{customer_id}"}
            ],
        }
    )

    dummy_openai: DummyOpenAIService = app.extensions["openai_service"]
    dummy_openai.reply = AssistantResponse(
        reply_text="", function_calls=[AssistantFunctionCall(name="lookup_customer", arguments={"customer_id": "123"})]
    )
    dummy_openai.summary_text = "Cliente 123 localizado"

    response = client.post(
        "/webhook/whatsapp",
        data={"From": "whatsapp:+549222222", "To": bot["twilio_phone_number"], "Body": "Consulta"},
    )

    assert response.status_code == 200
    assert "Cliente 123 localizado" in response.get_data(as_text=True)

    dummy_horizon: DummyHorizonService = app.extensions["horizon_service"]
    assert dummy_horizon.last_action == "lookup_customer"
    assert dummy_horizon.last_arguments == {"customer_id": "123"}
