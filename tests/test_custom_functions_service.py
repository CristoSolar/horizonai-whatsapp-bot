from __future__ import annotations

from typing import Any, Dict

from app.services.custom_functions_service import CustomFunctionsService


class _FakeRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    def get(self, key: str):
        return self.store.get(key)


def _base_arguments() -> Dict[str, Any]:
    return {
        "servicio": {"comuna": "santiago"},
        "vehiculo": {
            "marca": "Toyota",
            "modelo": "Yaris",
            "anio": 2022,
            "combustible": "bencina",
            "start_stop": "si",
        },
        "cliente": {
            "nombre": "Juan",
            "apellido": "Perez",
            "telefono": "+56912345678",
            "correo": "juan@example.com",
            "direccion": "Av Siempre Viva 123",
            "referencia": "Depto 2",
        },
        "estado_flujo": "agendando",
    }


def test_service_lead_extraction_sends_flow_history_on_create(monkeypatch):
    service = CustomFunctionsService(redis_client=_FakeRedis(), horizon_api_token="token")
    captured: Dict[str, Any] = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return {"id": 101}

    monkeypatch.setattr(service, "_create_horizon_lead", _fake_create)
    monkeypatch.setattr(service, "_get_horizon_lead", lambda *args, **kwargs: {"id": 101})

    args = _base_arguments()
    args["flow_history"] = [
        {"role": "system", "content": "internal"},
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": {"text": "Te ayudo"}},
        {"role": "tool", "content": "ignored"},
    ]

    result = service._handle_service_lead_extraction(args, bot_context={"lead_procedencia": "whatsapp_bot"})

    assert result["success"] is True
    assert result["lead_status"] == "created"
    assert captured["procedencia"] == "whatsapp_bot"
    assert captured["flow_history"] == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": {"text": "Te ayudo"}},
    ]


def test_service_lead_extraction_updates_existing_lead_with_flow_history(monkeypatch):
    service = CustomFunctionsService(redis_client=_FakeRedis(), horizon_api_token="token")
    captured: Dict[str, Any] = {}

    monkeypatch.setattr(service, "_get_lead_id_from_redis", lambda _phone: 999)

    def _fake_update(*, lead_id, payload, token_override=None):
        captured["lead_id"] = lead_id
        captured["payload"] = payload
        captured["token_override"] = token_override
        return {"id": 999}

    monkeypatch.setattr(service, "_update_horizon_lead", _fake_update)
    monkeypatch.setattr(
        service,
        "_create_horizon_lead",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not create lead when one exists")),
    )
    monkeypatch.setattr(service, "_get_horizon_lead", lambda *args, **kwargs: {"id": 999})

    args = _base_arguments()
    result = service._handle_service_lead_extraction(
        args,
        bot_context={
            "conversation_history": [
                {"role": "user", "content": "Hola"},
                {"role": "assistant", "content": "Te ayudo"},
            ]
        },
    )

    assert result["success"] is True
    assert result["lead_id"] == 999
    assert result["lead_status"] == "updated"
    assert captured["lead_id"] == 999
    assert captured["payload"]["flow_history"] == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Te ayudo"},
    ]


def test_resolve_flow_history_accepts_aliases():
    service = CustomFunctionsService(redis_client=_FakeRedis(), horizon_api_token="token")

    history = service._resolve_flow_history(
        {"messages": [{"role": "user", "content": "hola"}]},
        bot_context={},
    )

    assert history == [{"role": "user", "content": "hola"}]
