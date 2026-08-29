"""Dos entradas del registry pueden compartir número; el orden del hash no decide.

Pasó en producción: una entrada vieja con el mismo número que CFMoto y sin prompt
quedó primera tras un RESTORE de Redis, y el número real resolvía a ella.
"""
from __future__ import annotations

import pytest

from app.routes.whatsapp import _find_bot_by_number


NUMERO = "+15559015856"

BUENO = {
    "id": "bot-vivo",
    "name": "CFMoto",
    "twilio_phone_number": NUMERO,
    "instructions": "Sos el asistente de CFMoto.",
    "assistant_id": "",
}

BASURA = {
    "id": "bot-viejo",
    "name": "CFMoto",
    "twilio_phone_number": NUMERO,
    "instructions": None,
    "assistant_id": "asst_muerto",
}


class RepoFalso:
    def __init__(self, bots) -> None:
        self._bots = bots

    def list_bots(self):
        return list(self._bots)


@pytest.mark.parametrize("orden", [[BASURA, BUENO], [BUENO, BASURA]])
def test_gana_la_entrada_con_prompt(orden):
    bot = _find_bot_by_number(RepoFalso(orden), f"whatsapp:{NUMERO}")

    assert bot["id"] == "bot-vivo"


def test_sin_coincidencias_devuelve_none():
    assert _find_bot_by_number(RepoFalso([BUENO]), "whatsapp:+15550000000") is None


def test_numero_vacio_devuelve_none():
    assert _find_bot_by_number(RepoFalso([BUENO]), None) is None


def test_prompt_en_blanco_no_cuenta_como_prompt():
    en_blanco = dict(BUENO, id="bot-en-blanco", instructions="   ")
    bot = _find_bot_by_number(RepoFalso([en_blanco, BASURA]), f"whatsapp:{NUMERO}")

    # Ninguna sirve: devuelve la primera, pero el log ya avisó.
    assert bot["id"] == "bot-en-blanco"


def test_una_sola_entrada_sin_prompt_se_devuelve_igual():
    """Sin alternativa, es mejor seguir el camino de siempre que un 404 mudo."""
    bot = _find_bot_by_number(RepoFalso([BASURA]), f"whatsapp:{NUMERO}")

    assert bot["id"] == "bot-viejo"
