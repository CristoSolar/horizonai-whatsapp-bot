"""SQL-backed repository for whatsapp bot definitions stored in Horizon DB."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


SELECT_BASE = """
SELECT id, client_id, external_ref, twilio_phone_number, twilio_messaging_service_sid,
       twilio_account_sid, assistant_id, assistant_model, assistant_instructions,
       assistant_functions, openai_api_key, horizon_actions, metadata, status,
       created_at, updated_at
  FROM gestion_whatsappbot
"""


class SQLBotRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, bot_id: str) -> Optional[Dict[str, Any]]:
        sql = SELECT_BASE + " WHERE id = :id"
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), {"id": bot_id})
            row = result.mappings().first()
            return dict(row) if row else None

    def list(self, *, client_id: str | None = None) -> Iterable[Dict[str, Any]]:
        if client_id:
            sql = SELECT_BASE + " WHERE client_id = :cid ORDER BY created_at DESC"
            params = {"cid": client_id}
        else:
            sql = SELECT_BASE + " ORDER BY created_at DESC"
            params = {}
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            for row in result.mappings():
                yield dict(row)

    def find_by_twilio_number(self, number: str) -> Optional[Dict[str, Any]]:
        sql = SELECT_BASE + " WHERE twilio_phone_number = :num"
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), {"num": number})
            row = result.mappings().first()
            return dict(row) if row else None

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:  # type: ignore[no-untyped-def]
        # row is a sqlalchemy RowMapping when using .m or .mappings()
        return dict(row)
