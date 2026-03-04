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

    # Initialize client data manager (namespaced per bot)
    logger.info(f"🗃️ Initializing client data manager...")
    client_data_manager = ClientDataManager(redis_extension.client, namespace=bot_id)
    
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

    _try_auto_dispatch_bateriasya_lead(
        bot=bot,
        user_number=user_number,
        client_data_manager=client_data_manager,
        client_data=client_data,
    )

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
            user_number=user_number,
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
            
            # Define executor for subsequent tool calls if the run asks again
            def _on_tool_calls(calls: List[AssistantFunctionCall]) -> List[ToolResult]:
                return _execute_tool_calls(
                    bot=bot,
                    horizon_service=horizon_service,
                    defined_actions=bot.get("horizon_actions", []),
                    function_calls=calls,
                    user_number=user_number,
                )

            # Submit tool outputs and get final response (supports multi-round tools)
            if tool_outputs:
                reply_text = openai_service.submit_tool_outputs_and_wait(
                    thread_id=assistant_response.thread_id,
                    run_id=assistant_response.run_id,
                    tool_outputs=tool_outputs,
                    on_tool_calls=_on_tool_calls,
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


def _resolve_twilio_auth_token_from_metadata(bot_metadata: Dict[str, Any]) -> Optional[str]:
    token = bot_metadata.get("twilio_auth_token")
    if token:
        return token

    token_ref = bot_metadata.get("twilio_auth_token_ref")
    if not token_ref:
        return None

    token_map = current_app.config.get("TWILIO_AUTH_TOKEN_REFS") or {}
    resolved = token_map.get(token_ref)
    return resolved or None


def _resolve_bot_twilio_credentials(bot: Dict[str, Any]) -> Dict[str, Optional[str]]:
    metadata = bot.get("metadata") or {}
    return {
        "twilio_account_sid": metadata.get("twilio_account_sid") or bot.get("twilio_account_sid"),
        "twilio_auth_token": _resolve_twilio_auth_token_from_metadata(metadata),
        "twilio_messaging_service_sid": metadata.get("twilio_messaging_service_sid") or bot.get("twilio_messaging_service_sid"),
        "twilio_from_whatsapp": metadata.get("twilio_from_whatsapp") or bot.get("twilio_phone_number"),
    }


def _execute_tool_calls(
    *,
    bot: Dict[str, Any],
    horizon_service: HorizonService,
    defined_actions: Iterable[Dict[str, Any]],
    function_calls: List[AssistantFunctionCall],
    user_number: str,
) -> List[ToolResult]:
    """Execute tool calls, checking custom functions first, then Horizon actions."""
    
    # List of custom function names
    custom_functions = [
        "extract_hori_bateriasya_data",
        # Orquestación de agendas/CRM
        "listar_vendedores",
        "buscar_disponibilidad",
        "agendar_cita",
    ]
    
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
    
    # Get bot-specific configuration from metadata
    bot_metadata = bot.get("metadata") or {}
    horizon_api_token = bot_metadata.get("horizon_api_token") or current_app.config.get("HORIZON_API_KEY")
    # Override token for specific assistant if provided (per user request)
    try:
        assistant_id = bot.get("assistant_id")
        per_assistant_tokens = {
            # Token provisto por el cliente para este asistente
            "asst_1CYCRroCYaf2oeOWU7KGsih9": "f2W3tldUJqnkABs9ndT1pfMWYDF0AXTjPk0HVtyz5iX1TO8mEit8qyXO952eqxUR",
        }
        if assistant_id in per_assistant_tokens:
            horizon_api_token = per_assistant_tokens[assistant_id]
    except Exception:
        pass
    twilio_template_sid = bot_metadata.get("twilio_template_sid")
    twilio_messaging_service_sid = bot_metadata.get("twilio_messaging_service_sid") or bot.get("twilio_messaging_service_sid")
    sucursal_phone_map = bot_metadata.get("sucursal_phone_map") or {}
    
    custom_functions_service = CustomFunctionsService(
        twilio_service=twilio_service,
        redis_client=redis_client,
        horizon_api_token=horizon_api_token,
        twilio_template_sid=twilio_template_sid,
        twilio_messaging_service_sid=twilio_messaging_service_sid,
        sucursal_phone_map=sucursal_phone_map,
    )

    twilio_credentials = _resolve_bot_twilio_credentials(bot)
    
    for call in function_calls:
        # Check if it's a custom function
        if call.name in custom_functions:
            logger.info(f"🔧 Executing custom function: {call.name}")
            logger.info(f"   Arguments: {call.arguments}")
            bot_context = {
                "bot_id": bot.get("id"),
                "twilio_phone_number": bot.get("twilio_phone_number"),
                "user_number": user_number,
                "twilio_account_sid": twilio_credentials.get("twilio_account_sid"),
                "twilio_auth_token": twilio_credentials.get("twilio_auth_token"),
                "twilio_messaging_service_sid": twilio_credentials.get("twilio_messaging_service_sid"),
                "twilio_from_whatsapp": twilio_credentials.get("twilio_from_whatsapp"),
            }
            result = custom_functions_service.execute_custom_function(
                function_name=call.name,
                arguments=call.arguments,
                bot_context=bot_context,
            )
            logger.info(f"   Result: {result}")
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


def _try_auto_dispatch_bateriasya_lead(
    *,
    bot: Dict[str, Any],
    user_number: str,
    client_data_manager: ClientDataManager,
    client_data: Dict[str, Any],
) -> None:
    assistant_id = (bot.get("assistant_id") or "").strip()
    bot_name = (bot.get("name") or "").lower()
    is_bateriasya = ("bateria" in bot_name) or (assistant_id == "asst_svobnYajdAylQaM5Iqz8Dof3")
    if not is_bateriasya:
        return

    if client_data.get("notification_sent"):
        return

    required_fields = ["comuna", "marca", "modelo", "año", "combustible", "start_stop", "nombre", "telefono"]
    missing = [field for field in required_fields if not client_data.get(field)]
    if missing:
        return

    try:
        twilio_extension = current_app.extensions.get("twilio_extension")
        from .twilio_service import TwilioMessagingService

        twilio_service = TwilioMessagingService(twilio_extension) if twilio_extension else None
        twilio_credentials = _resolve_bot_twilio_credentials(bot)
        bot_metadata = bot.get("metadata") or {}
        horizon_api_token = bot_metadata.get("horizon_api_token") or current_app.config.get("HORIZON_API_KEY")
        twilio_template_sid = bot_metadata.get("twilio_template_sid")
        twilio_messaging_service_sid = bot_metadata.get("twilio_messaging_service_sid") or bot.get("twilio_messaging_service_sid")
        sucursal_phone_map = bot_metadata.get("sucursal_phone_map") or {}

        service = CustomFunctionsService(
            twilio_service=twilio_service,
            redis_client=redis_extension.client,
            horizon_api_token=horizon_api_token,
            twilio_template_sid=twilio_template_sid,
            twilio_messaging_service_sid=twilio_messaging_service_sid,
            sucursal_phone_map=sucursal_phone_map,
        )

        full_name = str(client_data.get("nombre", "")).strip()
        name_parts = [part for part in full_name.split() if part]
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        payload = {
            "servicio": {
                "comuna": client_data.get("comuna"),
            },
            "vehiculo": {
                "marca": client_data.get("marca"),
                "modelo": client_data.get("modelo"),
                "anio": int(client_data.get("año")) if str(client_data.get("año", "")).isdigit() else client_data.get("año"),
                "combustible": str(client_data.get("combustible", "")).lower().replace("é", "e"),
                "start_stop": "si" if str(client_data.get("start_stop", "")).lower() in {"sí", "si", "true", "1"} else "no",
            },
            "cliente": {
                "nombre": first_name,
                "apellido": last_name,
                "rut": client_data.get("rut", "N/A"),
                "direccion": client_data.get("direccion", "N/A"),
                "referencia": client_data.get("referencia", "N/A"),
                "telefono": client_data.get("telefono"),
                "correo": client_data.get("correo", "sin-correo@pendiente.cl"),
            },
            "estado_flujo": "agendando",
        }
        bot_context = {
            "bot_id": bot.get("id"),
            "twilio_phone_number": bot.get("twilio_phone_number"),
            "user_number": user_number,
            "twilio_account_sid": twilio_credentials.get("twilio_account_sid"),
            "twilio_auth_token": twilio_credentials.get("twilio_auth_token"),
            "twilio_messaging_service_sid": twilio_credentials.get("twilio_messaging_service_sid"),
            "twilio_from_whatsapp": twilio_credentials.get("twilio_from_whatsapp"),
        }

        result = service.execute_custom_function(
            function_name="extract_hori_bateriasya_data",
            arguments=payload,
            bot_context=bot_context,
        )

        if result.get("success"):
            client_data_manager.update_client_data(user_number, "notification_sent", True)
            if result.get("message_sid"):
                client_data_manager.update_client_data(user_number, "notification_message_sid", result.get("message_sid"))
            if result.get("target_phone"):
                client_data_manager.update_client_data(user_number, "notification_target_phone", result.get("target_phone"))
            logger.info(f"✅ Auto-dispatch BateriasYa ejecutado para {user_number}: {result}")
        else:
            logger.warning(f"⚠️ Auto-dispatch BateriasYa sin éxito para {user_number}: {result}")
    except Exception as exc:
        logger.error(f"❌ Error en auto-dispatch BateriasYa para {user_number}: {exc}")
