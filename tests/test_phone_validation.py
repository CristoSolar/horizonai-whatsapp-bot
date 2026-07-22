"""Tests for phone validity used by the WhatsApp user_number fallback."""
from __future__ import annotations

from app.services.custom_functions_service import CustomFunctionsService as S


def test_looks_like_phone_accepts_real_numbers():
    assert S._looks_like_phone("978493528")
    assert S._looks_like_phone("+56978493528")
    assert S._looks_like_phone("56 9 7849 3528")


def test_looks_like_phone_rejects_prose_and_empty():
    assert not S._looks_like_phone("El mismo que le escribo")
    assert not S._looks_like_phone("")
    assert not S._looks_like_phone(None)
    assert not S._looks_like_phone("123")  # too few digits
