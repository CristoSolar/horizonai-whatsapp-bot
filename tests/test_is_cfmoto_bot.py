from __future__ import annotations

from app.services.conversation_service import _is_cfmoto_bot


def test_cfmoto_detected_by_name():
    assert _is_cfmoto_bot({"name": "CFMOTO Chile"}) is True


def test_cfmoto_detected_by_metadata_token():
    assert _is_cfmoto_bot({"metadata": {"cfmoto_horizon_api_token": "tok"}}) is True


def test_cfmoto_detected_by_procedencia():
    assert _is_cfmoto_bot({"metadata": {"lead_procedencia": "whatsapp_cfmoto"}}) is True


def test_bateriasya_not_cfmoto():
    # Regression guard: a non-CFMOTO bot must NOT pick up the CFMOTO env token in sync.
    assert _is_cfmoto_bot({"name": "BateriasYa", "metadata": {"lead_procedencia": "whatsapp"}}) is False
