"""Redis-backed repository to manage bot metadata."""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

BOT_COLLECTION_KEY = "bots:registry"


class BotRepository:
    """CRUD operations for bot metadata stored in Redis."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def list_bots(self) -> List[Dict[str, Any]]:
        records = self._redis.hvals(BOT_COLLECTION_KEY)
        return [json.loads(record) for record in records]

    def get_bot(self, bot_id: str) -> Optional[Dict[str, Any]]:
        payload = self._redis.hget(BOT_COLLECTION_KEY, bot_id)
        return json.loads(payload) if payload else None

    def create_bot(self, bot_data: Dict[str, Any]) -> Dict[str, Any]:
        bot_id = bot_data.get("id") or uuid.uuid4().hex
        bot_data = {**bot_data, "id": bot_id}
        self._redis.hset(BOT_COLLECTION_KEY, bot_id, json.dumps(bot_data))
        return bot_data

    def update_bot(self, bot_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_bot(bot_id)
        if not current:
            return None
        current.update({k: v for k, v in updates.items() if v is not None})
        self._redis.hset(BOT_COLLECTION_KEY, bot_id, json.dumps(current))
        return current

    def delete_bot(self, bot_id: str) -> bool:
        return bool(self._redis.hdel(BOT_COLLECTION_KEY, bot_id))

    def clear(self) -> None:
        self._redis.delete(BOT_COLLECTION_KEY)
