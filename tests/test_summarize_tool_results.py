"""Chat Completions rechaza mensajes de rol "tool" sin su assistant con tool_calls.

Pasó en producción desde el 27/08: el lead se creaba bien y el cliente veía
"Lo siento, hubo un error al procesar tu mensaje" justo al completar sus datos.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import create_app
from app.services.openai_service import OpenAIAssistantService, ToolResult


BOT = {"instructions": "Sos el asistente.", "openai_model": "gpt-4.1-mini"}


class ClienteFalso:
    """Imita al cliente de OpenAI y rechaza lo mismo que rechaza la API real."""

    def __init__(self) -> None:
        self.mensajes_enviados = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, **kwargs):
        self.mensajes_enviados = messages
        for i, m in enumerate(messages):
            if m.get("role") == "tool":
                raise AssertionError(
                    f"messages[{i}] con role 'tool' sin tool_calls previo — la API da 400"
                )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Listo, un ejecutivo te contacta.", tool_calls=None)
                )
            ]
        )


class ExtensionFalsa:
    def __init__(self, client) -> None:
        self.client = client


@pytest.fixture()
def app():
    return create_app("testing")


def _servicio(cliente):
    return OpenAIAssistantService(ExtensionFalsa(cliente))


def test_historial_envenenado_no_tumba_el_turno(app):
    """Las sesiones ya guardadas en Redis traen mensajes de rol tool."""
    cliente = ClienteFalso()
    conversacion = [
        {"role": "user", "content": "me interesa la 450MT"},
        {"role": "tool", "name": "extract_hori_cfmoto_data", "content": '{"lead_id": 24357}'},
        {"role": "user", "content": "sí, Santiago, contado"},
    ]

    with app.app_context():
        texto = _servicio(cliente).summarize_tool_results(
            bot=BOT,
            conversation=conversacion,
            tool_results=[ToolResult(name="extract_hori_cfmoto_data", content='{"lead_id": 24357}')],
        )

    assert texto == "Listo, un ejecutivo te contacta."
    assert [m["role"] for m in cliente.mensajes_enviados] == [
        "system", "user", "user", "system",
    ]


def test_el_resultado_de_la_funcion_llega_como_system(app):
    cliente = ClienteFalso()

    with app.app_context():
        _servicio(cliente).summarize_tool_results(
            bot=BOT,
            conversation=[{"role": "user", "content": "hola"}],
            tool_results=[ToolResult(name="crear_lead", content='{"lead_id": 24357}')],
        )

    ultimo = cliente.mensajes_enviados[-1]
    assert ultimo["role"] == "system"
    assert "crear_lead" in ultimo["content"]
    assert "24357" in ultimo["content"]


def test_build_messages_conserva_los_roles_validos(app):
    conversacion = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¿en qué te ayudo?"},
        {"role": "system", "content": "datos del cliente"},
    ]

    mensajes = OpenAIAssistantService._build_messages("instrucciones", conversacion)

    assert mensajes[0] == {"role": "system", "content": "instrucciones"}
    assert mensajes[1:] == conversacion
