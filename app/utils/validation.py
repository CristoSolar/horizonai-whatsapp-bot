"""Validation helpers for API payloads."""
from __future__ import annotations

from typing import Iterable, Mapping


class ValidationError(ValueError):
    """Raised when input payload does not match expected shape."""


def require_fields(payload: Mapping[str, object], fields: Iterable[str]) -> None:
    missing = [field for field in fields if not payload.get(field)]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")
