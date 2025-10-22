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


@blueprint.post("/webhook/whatsapp")
def receive_whatsapp() -> Response:
    """Handle incoming WhatsApp message webhook from Twilio."""
    
    # Log incoming request for debugging
    print(f"📨 Webhook received:")
    print(f"   From: {request.values.get('From')}")
    print(f"   To: {request.values.get('To')}")
    print(f"   Body: {request.values.get('Body')}")
    print(f"   All params: {dict(request.values)}")
    
    repository = _get_repository()

    bot_id = request.args.get("bot_id") or request.values.get("BotId")
    if bot_id:
        print(f"🔍 Looking for bot by ID: {bot_id}")
        bot = repository.get_bot(bot_id)
        if not bot:
            print(f"❌ Bot '{bot_id}' not found")
            raise BadRequest(f"Bot '{bot_id}' not found")
    else:
        to_number = request.values.get("To")
        print(f"🔍 Looking for bot by number: {to_number}")
        bot = _find_bot_by_number(repository, to_number)
        if not bot:
            print(f"❌ No bot found for number: {to_number}")
            raise BadRequest("No bot found for the provided WhatsApp number")

    print(f"✅ Bot found: {bot['id']} - {bot.get('name', 'No name')}")

    from_number = _normalize_number(request.values.get("From"))
    body = request.values.get("Body", "").strip()
    
    print(f"📞 Processing message:")
    print(f"   From: {from_number}")
    print(f"   Message: {body}")
    
    if not body:
        print("❌ Empty message body")
        raise BadRequest("Body is required")

    try:
        print(f"🤖 Generating response...")
        reply_text = handle_incoming_message(
            bot_id=bot["id"],
            user_number=from_number or "unknown",
            message=body,
            repository=repository,
        )
        print(f"✅ Response generated: {reply_text[:100]}...")
        
    except Exception as e:
        print(f"❌ Error generating response: {e}")
        import traceback
        traceback.print_exc()
        reply_text = "Lo siento, hubo un error al procesar tu mensaje."

    twiml = MessagingResponse()
    twiml.message(reply_text)
    print(f"📤 Sending TwiML response")
    return Response(str(twiml), mimetype="application/xml")
