"""Webhook endpoints to receive WhatsApp events from Twilio."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from flask import Blueprint, Response, current_app, request
from twilio.twiml.messaging_response import MessagingResponse
from werkzeug.exceptions import BadRequest

from ..extensions import redis_extension
from ..repositories import BotRepository
from ..services.conversation_service import (
    handle_incoming_message,
    human_agent_has_control,
)
from ..services.horizon_config_loader import HorizonConfigLoader
from ..services.outbound_whatsapp_service import OutboundWhatsAppService

blueprint = Blueprint("whatsapp", __name__)
logger = logging.getLogger(__name__)


def _get_horizon_loader() -> Optional[HorizonConfigLoader]:
    """Build a HorizonConfigLoader from the current Flask app config, if configured."""
    try:
        base_url = current_app.config.get("HORIZON_BASE_URL")
        api_key = current_app.config.get("HORIZON_API_KEY")
        if not base_url or not api_key:
            return None
        return HorizonConfigLoader(
            horizon_base_url=base_url,
            api_token=api_key,
            redis_client=redis_extension.client,
        )
    except Exception as exc:
        logger.warning("[whatsapp] No se pudo crear HorizonConfigLoader: %s", exc)
        return None


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


def _resolve_tenant_id(bot: dict) -> str:
    metadata = bot.get("metadata") or {}
    return (
        metadata.get("tenant_id")
        or bot.get("client_id")
        or bot.get("id")
    )


def _register_last_inbound(bot: dict, from_number: Optional[str]) -> None:
    if not from_number:
        return
    tenant_id = _resolve_tenant_id(bot)
    service = OutboundWhatsAppService(redis_extension.client)
    service.mark_last_inbound(
        tenant_id=tenant_id,
        to_e164=from_number,
        at=datetime.now(UTC),
    )


@blueprint.get("/webhook/whatsapp")
def webhook_health() -> Response:
    """Health check for webhook endpoint."""
    return Response("Webhook endpoint is working!", mimetype="text/plain")


@blueprint.post("/webhook/whatsapp")
def receive_whatsapp() -> Response:
    """Handle incoming WhatsApp message webhook from Twilio."""
    
    # Log incoming request for debugging
    logger.info(f"📨 Webhook received:")
    logger.info(f"   From: {request.values.get('From')}")
    logger.info(f"   To: {request.values.get('To')}")
    logger.info(f"   Body: {request.values.get('Body')}")
    logger.info(f"   All params: {dict(request.values)}")
    
    repository = _get_repository()

    bot_id = request.args.get("bot_id") or request.values.get("BotId")
    if bot_id:
        logger.info(f"🔍 Looking for bot by ID: {bot_id}")
        bot = repository.get_bot(bot_id)
        if not bot:
            logger.error(f"❌ Bot '{bot_id}' not found")
            raise BadRequest(f"Bot '{bot_id}' not found")
    else:
        to_number = request.values.get("To")
        logger.info(f"🔍 Looking for bot by number: {to_number}")
        bot = _find_bot_by_number(repository, to_number)

        # Fallback: Horizon es la fuente de verdad cuando Redis no tiene el bot
        if not bot:
            logger.info(
                "🌐 Bot no encontrado en Redis, consultando Horizon para número: %s",
                to_number,
            )
            loader = _get_horizon_loader()
            phone = _normalize_number(to_number)
            if loader and phone:
                horizon_config = loader.get_bot_config(phone)
                if horizon_config:
                    # Persistir en bots:registry para que get_bot(id) funcione
                    # dentro de handle_incoming_message y en llamadas posteriores.
                    bot = repository.create_bot(horizon_config)
                    logger.info(
                        "✅ Config obtenida de Horizon y cacheada en Redis para phone=%s bot_id=%s",
                        phone,
                        bot.get("id"),
                    )
                else:
                    logger.warning(
                        "⚠️ Horizon tampoco tiene config para phone=%s", phone
                    )

        if not bot:
            logger.error(f"❌ No bot found for number: {to_number}")
            raise BadRequest("No bot found for the provided WhatsApp number")

    logger.info(f"✅ Bot found: {bot['id']} - {bot.get('name', 'No name')}")

    from_number = _normalize_number(request.values.get("From"))
    body = request.values.get("Body", "").strip()

    _register_last_inbound(bot, from_number)
    
    logger.info(f"📞 Processing message:")
    logger.info(f"   From: {from_number}")
    logger.info(f"   Message: {body}")
    
    if not body:
        logger.error("❌ Empty message body")
        raise BadRequest("Body is required")

    # Respect human handoff: if an agent took control in the CRM, stay silent.
    if human_agent_has_control(bot, from_number or "unknown"):
        logger.info("🛑 Human control active — bot skipping reply for %s", from_number)
        # Empty TwiML => Twilio sends no message.
        return Response(str(MessagingResponse()), mimetype="application/xml")

    try:
        logger.info(f"🤖 Generating response...")
        reply_text = handle_incoming_message(
            bot_id=bot["id"],
            user_number=from_number or "unknown",
            message=body,
            repository=repository,
        )
        logger.info(f"✅ Response generated: {reply_text[:100]}...")
        
    except Exception as e:
        logger.error(f"❌ Error generating response: {e}")
        import traceback
        logger.error(traceback.format_exc())
        reply_text = "Lo siento, hubo un error al procesar tu mensaje."

    twiml = MessagingResponse()
    twiml.message(reply_text)
    logger.info(f"📤 Sending TwiML response")
    return Response(str(twiml), mimetype="application/xml")
