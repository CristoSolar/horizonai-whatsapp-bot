"""High-level orchestration for WhatsApp conversations."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from flask import current_app
from werkzeug.exceptions import BadRequest, NotFound

from ..extensions import redis_extension
from ..repositories import BotRepository
from ..extensions import db_extension
from ..repositories.sql_bot_repository import SQLBotRepository
from .horizon_service import HorizonService
from .client_data_service import ClientDataManager
from .custom_functions_service import CustomFunctionsService
from .openai_service import (
    AssistantFunctionCall,
    AssistantResponse,
    OpenAIAssistantService,
    ToolResult,
)

SESSION_KEY_PATTERN = "session:{bot_id}:{user_number}"
MAX_HISTORY_MESSAGES = 20

logger = logging.getLogger(__name__)


def handle_incoming_message(
    *,
    bot_id: str,
    user_number: str,
    message: str,
    repository: Optional[BotRepository] = None,
    openai_service: Optional[OpenAIAssistantService] = None,
    horizon_service: Optional[HorizonService] = None,
) -> str:
    logger.info(f"🎯 handle_incoming_message called:")
    logger.info(f"   bot_id: {bot_id}")
    logger.info(f"   user_number: {user_number}")
    logger.info(f"   message: {message}")
    
    if not user_number:
        raise BadRequest("Missing sender number")
    if not message:
        raise BadRequest("Message body is required")

    repository = repository or BotRepository(redis_extension.client)
    
    # Initialize client data manager
    logger.info(f"🗃️ Initializing client data manager...")
    client_data_manager = ClientDataManager(redis_extension.client)
    
    # Extract information from current message
    logger.info(f"🔍 Extracting info from message...")
    extracted_info = client_data_manager.extract_info_from_message(message)
    logger.info(f"   Extracted: {extracted_info}")
    
    # Update client data with any extracted information
    for field, value in extracted_info.items():
        logger.info(f"   Updating {field}: {value}")
        client_data_manager.update_client_data(user_number, field, value)
    
    # Get current client data
    client_data = client_data_manager.get_client_data(user_number)
    logger.info(f"💾 Current client data: {client_data}")
    
    bot = repository.get_bot(bot_id)
    # Fallback: if not found in Redis, attempt database lookup (source of truth)
    if not bot:
        try:
            engine = db_extension.engine  # may raise if not configured
            sql_repo = SQLBotRepository(engine)
            bot = sql_repo.get(bot_id)
            if bot:
                # Cache minimal snapshot in Redis for faster subsequent retrievals
                repository.create_bot({
                    "id": bot.get("id"),
                    "name": bot.get("external_ref") or bot.get("id"),
                    "instructions": bot.get("assistant_instructions"),
                    "assistant_id": bot.get("assistant_id"),
                    "openai_model": bot.get("assistant_model"),
                    "assistant_functions": bot.get("assistant_functions") or [],
                    "horizon_actions": bot.get("horizon_actions") or [],
                    "twilio_phone_number": bot.get("twilio_phone_number"),
                })
        except Exception:  # pragma: no cover
            pass
    if not bot:
        raise NotFound(f"Bot '{bot_id}' not found")

    conversation = _load_conversation(bot_id=bot_id, user_number=user_number)
    conversation.append({"role": "user", "content": message})

    # Construir mensaje de estado actualizado (slots) como mensaje de sistema adicional
    client_info = []
    if client_data:
        if client_data.get('marca'):
            client_info.append(f"Marca del vehículo: {client_data['marca']}")
        if client_data.get('modelo'):
            client_info.append(f"Modelo: {client_data['modelo']}")
        if client_data.get('año'):
            client_info.append(f"Año: {client_data['año']}")
        if client_data.get('combustible'):
            client_info.append(f"Combustible: {client_data['combustible']}")
        if client_data.get('start_stop'):
            client_info.append(f"Start-Stop: {client_data['start_stop']}")
        if client_data.get('comuna'):
            client_info.append(f"Comuna: {client_data['comuna']}")

    # Mensaje de sistema con slots actuales
    if client_info:
        estado_slots = "\n".join(client_info)
        system_state_msg = {
            "role": "system",
            "content": f"ESTADO ACTUAL DEL CLIENTE:\n{estado_slots}\n\nNO preguntes por información que ya tienes. Usa esta información para ayudar mejor al cliente."
        }
        # Insertar el mensaje de estado al inicio de la conversación (después del system original si existe)
        if conversation and conversation[0]["role"] == "system":
            conversation.insert(1, system_state_msg)
        else:
            conversation.insert(0, system_state_msg)

    openai_service = openai_service or current_app.extensions["openai_service"]
    assistant_response = openai_service.generate_reply(
        bot=bot,
        conversation=conversation,
        tool_definitions=bot.get("assistant_functions"),
        user_phone=user_number,
    )

    tool_results: List[ToolResult] = []
    if assistant_response.function_calls:
        horizon_service = horizon_service or current_app.extensions["horizon_service"]
        tool_results = _execute_tool_calls(
            bot=bot,
            horizon_service=horizon_service,
            defined_actions=bot.get("horizon_actions", []),
            function_calls=assistant_response.function_calls,
        )
        
        # If using assistants (thread_id and run_id present), submit tool outputs
        if assistant_response.thread_id and assistant_response.run_id:
            # Prepare tool outputs for submission
            tool_outputs = []
            for i, result in enumerate(tool_results):
                tool_output = {
                    "tool_call_id": assistant_response.tool_call_ids[i] if assistant_response.tool_call_ids and i < len(assistant_response.tool_call_ids) else None,
                    "output": result.content
                }
                if tool_output["tool_call_id"]:
                    tool_outputs.append(tool_output)
            
            # Submit tool outputs and get final response
            if tool_outputs:
                reply_text = openai_service.submit_tool_outputs_and_wait(
                    thread_id=assistant_response.thread_id,
                    run_id=assistant_response.run_id,
                    tool_outputs=tool_outputs
                )
            else:
                reply_text = "Lo siento, hubo un error procesando las acciones."
        else:
            # Using chat completions (not assistant), use old flow
            conversation.extend(
                {"role": "tool", "name": result.name, "content": result.content}
                for result in tool_results
            )
            reply_text = openai_service.summarize_tool_results(
                bot=bot,
                conversation=conversation,
                tool_results=tool_results,
            )
    else:
        reply_text = assistant_response.reply_text

    conversation.append({"role": "assistant", "content": reply_text})
    _save_conversation(bot_id=bot_id, user_number=user_number, conversation=conversation)

    return reply_text


def _load_conversation(*, bot_id: str, user_number: str) -> List[Dict[str, str]]:
    redis_client = redis_extension.client
    key = SESSION_KEY_PATTERN.format(bot_id=bot_id, user_number=user_number)
    payload = redis_client.get(key)
    if not payload:
        return []
    try:
        messages: List[Dict[str, str]] = json.loads(payload)
        return messages
    except json.JSONDecodeError:
        redis_client.delete(key)
        return []


def _save_conversation(*, bot_id: str, user_number: str, conversation: Iterable[Dict[str, str]]) -> None:
    redis_client = redis_extension.client
    key = SESSION_KEY_PATTERN.format(bot_id=bot_id, user_number=user_number)
    serialized = json.dumps(list(conversation)[-MAX_HISTORY_MESSAGES:])
    ttl = current_app.config.get("REDIS_SESSION_TTL_SECONDS")
    if ttl:
        redis_client.setex(key, ttl, serialized)
    else:
        redis_client.set(key, serialized)


def _execute_tool_calls(
    *,
    bot: Dict[str, Any],
    horizon_service: HorizonService,
    defined_actions: Iterable[Dict[str, Any]],
    function_calls: List[AssistantFunctionCall],
) -> List[ToolResult]:
    """Execute tool calls, checking custom functions first, then Horizon actions."""
    
    # List of custom function names
    custom_functions = ["extract_hori_bateriasya_data"]
    
    results: List[ToolResult] = []
    
    # Initialize custom functions service with Twilio and Redis
    try:
        twilio_extension = current_app.extensions.get("twilio_extension")
        from .twilio_service import TwilioMessagingService
        twilio_service = TwilioMessagingService(twilio_extension) if twilio_extension else None
    except Exception as e:
        logger.warning(f"Could not initialize Twilio service: {e}")
        twilio_service = None
    
    # Get Redis client for storing lead IDs
    redis_client = redis_extension.client
    
    # Get Horizon API token from config if available
    horizon_api_token = current_app.config.get("HORIZON_API_KEY")
    
    custom_functions_service = CustomFunctionsService(
        twilio_service=twilio_service,
        redis_client=redis_client,
        horizon_api_token=horizon_api_token,
    )
    
    for call in function_calls:
        # Check if it's a custom function
        if call.name in custom_functions:
            logger.info(f"Executing custom function: {call.name}")
            bot_context = {
                "bot_id": bot.get("id"),
                "twilio_phone_number": bot.get("twilio_phone_number"),
            }
            result = custom_functions_service.execute_custom_function(
                function_name=call.name,
                arguments=call.arguments,
                bot_context=bot_context,
            )
            results.append(ToolResult(name=call.name, content=json.dumps(result)))
        else:
            # Execute as Horizon action
            logger.info(f"Executing Horizon action: {call.name}")
            result = horizon_service.execute_action(
                action_name=call.name,
                defined_actions=defined_actions,
                arguments=call.arguments,
            )
            results.append(ToolResult(name=call.name, content=json.dumps(result)))
    
    return results
