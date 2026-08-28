"""El snapshot que cachea SQL en Redis tiene que conservar `metadata`.

Sin `metadata` el bot se levanta sin extractor, sin auto-dispatch y sin plantilla
de notificacion al vendedor, y no falla: responde peor, en silencio.
"""
from __future__ import annotations

import json

import pytest

from app import create_app
from app.extensions import db_extension, redis_extension
from app.repositories import BotRepository
from app.services import conversation_service
from app.services.openai_service import AssistantResponse


BOT_ID = "bot000000000000000000000000prueba"

METADATA = {
    "twilio_template_sid": "HX00000000000000000000000000000001",
    "auto_dispatch_enabled": True,
    "sucursal_phone_map": {"santiago": "+56911111111"},
    "extraction_keywords": ["bateria", "amperaje"],
}

FILA_SQL = {
    "id": BOT_ID,
    "client_id": "42",
    "external_ref": "CFMoto",
    "twilio_phone_number": "whatsapp:+56922222222",
    "twilio_messaging_service_sid": "MG0000000000000000000000000000000",
    "twilio_account_sid": "AC00000000000000000000000000000001",
    "assistant_id": "",
    "assistant_model": "gpt-4.1-mini",
    "assistant_instructions": "Sos el asistente de CFMoto.",
    "assistant_functions": [],
    "horizon_actions": [],
    "metadata": METADATA,
    "status": "active",
}


class RepoSQLFalso:
    def __init__(self, engine) -> None:  # noqa: D107 - firma que espera el codigo
        self._engine = engine

    def get(self, bot_id: str):
        return dict(FILA_SQL) if bot_id == BOT_ID else None


class OpenAIFalso:
    def generate_reply(self, **kwargs):
        return AssistantResponse(reply_text="Hola", function_calls=[])

    def summarize_tool_results(self, **kwargs):
        return "listo"


class HorizonFalso:
    def execute_action(self, **kwargs):
        return {}


@pytest.fixture()
def app():
    app = create_app("testing")
    yield app
    redis_extension.client.flushdb()


def _responder(app, monkeypatch, *, metadata):
    fila = dict(FILA_SQL, metadata=metadata)
    monkeypatch.setattr(RepoSQLFalso, "get", lambda self, bot_id: dict(fila))
    monkeypatch.setattr(conversation_service, "SQLBotRepository", RepoSQLFalso)
    monkeypatch.setattr(db_extension, "_engine", object(), raising=False)

    with app.app_context():
        conversation_service.handle_incoming_message(
            bot_id=BOT_ID,
            user_number="whatsapp:+56933333333",
            message="Hola",
            openai_service=OpenAIFalso(),
            horizon_service=HorizonFalso(),
        )
    return BotRepository(redis_extension.client).get_bot(BOT_ID)


def test_snapshot_conserva_metadata(app, monkeypatch):
    guardado = _responder(app, monkeypatch, metadata=METADATA)

    assert guardado is not None
    assert guardado["metadata"] == METADATA
    assert guardado["client_id"] == "42"
    assert guardado["twilio_account_sid"] == FILA_SQL["twilio_account_sid"]
    assert guardado["twilio_messaging_service_sid"] == FILA_SQL["twilio_messaging_service_sid"]


def test_snapshot_deserializa_metadata_en_texto(app, monkeypatch):
    """Segun el driver, MySQL puede devolver la columna JSON como texto."""
    guardado = _responder(app, monkeypatch, metadata=json.dumps(METADATA))

    assert guardado["metadata"] == METADATA


@pytest.mark.parametrize("valor", [None, "", "{no es json}", "[1, 2]", 7])
def test_como_dict_devuelve_dict_ante_basura(valor):
    assert conversation_service._como_dict(valor) == {}
