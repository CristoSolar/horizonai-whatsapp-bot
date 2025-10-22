"""Webhook endpoints to receive WhatsApp events from Twilio."""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, Response, request
from twilio.twiml.messaging_response import MessagingResponse
from werkzeug.exceptions import BadRequest

from ..extensions import redis_extension
from ..repositories import BotRepository
from ..services.conversation_service import handle_incoming_message

blueprint = Blueprint("whatsapp", __name__)


def _get_repository() -> BotRepository:
    return BotRepository(redis_extension.client)


def _normalize_number(number: Optional[str]) -> Optional[str]:
    if not number:
        return None
    return number.replace("whatsapp:", "")


def _find_bot_by_number(repository: BotRepository, target_number: Optional[str]):
    normalized = _normalize_number(target_number)
    if not normalized:
        return None
    for bot in repository.list_bots():
        stored = _normalize_number(bot.get("twilio_phone_number"))
        if stored == normalized:
            return bot
    return None


@blueprint.post("/whatsapp")
def whatsapp_inbound():
    repository = _get_repository()

    bot_id = request.args.get("bot_id") or request.values.get("BotId")
    if bot_id:
        bot = repository.get_bot(bot_id)
        if not bot:
            raise BadRequest(f"Bot '{bot_id}' not found")
    else:
        bot = _find_bot_by_number(repository, request.values.get("To"))
        if not bot:
            raise BadRequest("No bot found for the provided WhatsApp number")

    from_number = _normalize_number(request.values.get("From"))
    body = request.values.get("Body", "").strip()
    if not body:
        raise BadRequest("Body is required")

    reply_text = handle_incoming_message(
        bot_id=bot["id"],
        user_number=from_number or "unknown",
        message=body,
        repository=repository,
    )

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(str(twiml), mimetype="application/xml")
