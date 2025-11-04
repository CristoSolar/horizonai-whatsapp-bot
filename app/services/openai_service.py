"""Business logic helpers for interacting with OpenAI assistants."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from flask import current_app

from ..extensions import OpenAIExtension


@dataclass
class AssistantFunctionCall:
    name: str
    arguments: Dict[str, Any]


@dataclass
class AssistantResponse:
    reply_text: str
    function_calls: List[AssistantFunctionCall]
    thread_id: Optional[str] = None
    run_id: Optional[str] = None
    tool_call_ids: Optional[List[str]] = None


@dataclass
class ToolResult:
    name: str
    content: str


class OpenAIAssistantService:
    """High level gateway to OpenAI's assistants and responses APIs."""

    def __init__(self, extension: OpenAIExtension) -> None:
        self._extension = extension

    # ------------------------------------------------------------------
    # Assistant lifecycle helpers
    # ------------------------------------------------------------------
    def create_assistant(
        self,
        *,
        name: str,
        instructions: str,
        model: Optional[str] = None,
        tools: Optional[Iterable[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        client = self._require_client()
        assistant = client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model or current_app.config.get("OPENAI_DEFAULT_MODEL"),
            tools=list(tools or []),
            metadata=metadata,
        )
        return _safe_to_dict(assistant)

    def update_assistant(self, assistant_id: str, **updates: Any) -> Dict[str, Any]:
        client = self._require_client()
        assistant = client.beta.assistants.update(assistant_id, **updates)
        return _safe_to_dict(assistant)

    # ------------------------------------------------------------------
    # Conversational helpers
    # ------------------------------------------------------------------
    def generate_reply(
        self,
        *,
        bot: Dict[str, Any],
        conversation: List[Dict[str, str]],
        tool_definitions: Optional[Iterable[Dict[str, Any]]] = None,
        user_phone: Optional[str] = None,
    ) -> AssistantResponse:
        client = self._extension.client
        if client is None:
            return AssistantResponse(
                reply_text=self._fallback_reply(conversation),
                function_calls=[],
            )

        instructions = bot.get("instructions") or current_app.config.get(
            "OPENAI_DEFAULT_INSTRUCTIONS"
        )
        model = bot.get("openai_model") or bot.get("model") or current_app.config.get(
            "OPENAI_DEFAULT_MODEL"
        )

        # Check if bot has assistant_id
        assistant_id = bot.get("assistant_id")
        
        if assistant_id:
            # Use assistant-based conversation with persistent thread
            return self._generate_assistant_reply(client, assistant_id, conversation, user_phone)
        else:
            # Fall back to regular chat completion
            input_messages = self._build_messages(instructions, conversation)
            
            response = client.chat.completions.create(
                model=model,
                messages=input_messages,
                tools=list(tool_definitions or []) if tool_definitions else None,
            )
            
            return self._parse_chat_response(response)

    def summarize_tool_results(
        self,
        *,
        bot: Dict[str, Any],
        conversation: List[Dict[str, str]],
        tool_results: List[ToolResult],
    ) -> str:
        client = self._extension.client
        if client is None:
            summary_parts = [
                "He ejecutado estas acciones:",
                *[f"- {result.name}: {result.content}" for result in tool_results],
            ]
            return "\n".join(summary_parts)

        instructions = bot.get("instructions") or current_app.config.get(
            "OPENAI_DEFAULT_INSTRUCTIONS"
        )
        model = bot.get("openai_model") or bot.get("model") or current_app.config.get(
            "OPENAI_DEFAULT_MODEL"
        )

        input_messages = self._build_messages(instructions, conversation)
        for result in tool_results:
            input_messages.append(
                {
                    "role": "tool",
                    "content": result.content,
                    "name": result.name,
                }
            )

        response = client.responses.create(model=model, input=input_messages)
        assistant_response = self._parse_response(response)
        return assistant_response.reply_text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _require_client(self):
        client = self._extension.client
        if client is None:
            raise RuntimeError(
                "OpenAI client not configured. Set OPENAI_API_KEY to enable assistant operations."
            )
        return client

    @staticmethod
    def _build_messages(
        instructions: str, conversation: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": instructions}
        ]
        messages.extend(conversation)
        return messages

    @staticmethod
    def _parse_response(response: Any) -> AssistantResponse:
        reply_segments: List[str] = []
        function_calls: List[AssistantFunctionCall] = []

        outputs = _safe_get_outputs(response)
        for item in outputs:
            item_type = item.get("type") or item.get("role")
            if item_type in {"output_text", "message"}:
                text = item.get("text") or _extract_text_content(item.get("content"))
                if text:
                    reply_segments.append(text)
            elif item_type == "tool_calls":
                for call in item.get("tool_calls", []):
                    function = call.get("function", {})
                    name = function.get("name")
                    raw_args = function.get("arguments") or {}
                    try:
                        arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except json.JSONDecodeError:
                        arguments = {"_raw": raw_args}
                    if name:
                        function_calls.append(AssistantFunctionCall(name=name, arguments=arguments))

        if not reply_segments and not function_calls:
            reply_segments.append("Gracias, estoy procesando tu solicitud.")

        return AssistantResponse(
            reply_text="\n".join(segment.strip() for segment in reply_segments if segment),
            function_calls=function_calls,
        )

    @staticmethod
    def _fallback_reply(conversation: List[Dict[str, str]]) -> str:
        if not conversation:
            return "Hola, ¿cómo puedo ayudarte hoy?"
        last_message = conversation[-1].get("content", "")
        return (
            "He recibido tu mensaje pero el asistente aún no está configurado. "
            f"Mensaje: {last_message}"
        )

    def _generate_assistant_reply(self, client, assistant_id: str, conversation: List[Dict[str, str]], user_phone: str = None) -> AssistantResponse:
        """Generate reply using OpenAI assistant with persistent thread per user."""
        try:
            # Get or create thread for this user
            thread_id = self._get_or_create_thread(client, user_phone, namespace=assistant_id)
            # Concurrency guard: avoid adding messages while a run is active
            from ..extensions import redis_extension
            redis_client = redis_extension.client
            active_run_key = f"oa:thread:{thread_id}:active_run"
            try:
                existing_run_id = redis_client.get(active_run_key)
                if existing_run_id:
                    # Verify status with API and wait briefly
                    try:
                        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=existing_run_id if isinstance(existing_run_id, str) else existing_run_id.decode('utf-8'))
                        import time
                        max_wait_secs = 5
                        waited = 0
                        while run.status in ["queued", "in_progress", "requires_action"] and waited < max_wait_secs:
                            time.sleep(0.5)
                            waited += 0.5
                            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                        if run.status in ["queued", "in_progress", "requires_action"]:
                            # Still active; return a soft notice
                            return AssistantResponse(
                                reply_text="Estoy finalizando la acción anterior, dame unos segundos y vuelve a intentarlo.",
                                function_calls=[]
                            )
                        else:
                            # Clear flag
                            try:
                                redis_client.delete(active_run_key)
                            except Exception:
                                pass
                    except Exception:
                        # If retrieve fails, clear flag and continue
                        try:
                            redis_client.delete(active_run_key)
                        except Exception:
                            pass
            except Exception:
                # If Redis not available, continue without guard
                pass
            
            # Add the latest message to the thread
            if conversation:
                latest_message = conversation[-1]
                if latest_message.get("role") == "user":
                    client.beta.threads.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content=latest_message.get("content", "")
                    )
            
            # Get current date context for additional instructions
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            chile_tz = ZoneInfo("America/Santiago")
            now = datetime.now(chile_tz)
            
            day_names = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
            month_names = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                          'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            day_name = day_names[now.weekday()]
            month_name = month_names[now.month - 1]
            
            current_date_str = f"{day_name}, {now.day} de {month_name} de {now.year}"
            current_iso = now.isoformat()
            
            # Create additional instructions with current date
            additional_instructions = f"""INFORMACIÓN TEMPORAL CRÍTICA:
- Fecha actual: {current_date_str}
- Año actual: {now.year}
- Fecha ISO: {current_iso}
- Día de la semana: {day_name}
- Mes: {month_name}

IMPORTANTE: Cuando calcules fechas o crees agendamientos, SIEMPRE usa el año {now.year}, NO años anteriores.
Si el usuario menciona "jueves", "viernes", etc., calcula la fecha en base a HOY ({current_date_str}, {now.year}).
Todos los timestamps en las funciones deben usar el año {now.year}."""
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"📅 Additional instructions being sent: {additional_instructions}")
            
            # Run the assistant with additional instructions
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
                additional_instructions=additional_instructions
            )
            # Mark run as active in Redis (with short TTL)
            try:
                redis_client.setex(active_run_key, 300, run.id)
            except Exception:
                pass
            
            # Wait for completion
            import time
            max_iterations = 60  # Prevent infinite loop
            iterations = 0
            
            while run.status in ["queued", "in_progress", "requires_action"] and iterations < max_iterations:
                iterations += 1
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                
                # Handle function calls
                if run.status == "requires_action":
                    required_action = run.required_action
                    if required_action and required_action.type == "submit_tool_outputs":
                        function_calls = []
                        tool_calls = required_action.submit_tool_outputs.tool_calls
                        
                        for tool_call in tool_calls:
                            if tool_call.type == "function":
                                function_name = tool_call.function.name
                                try:
                                    arguments = json.loads(tool_call.function.arguments)
                                except json.JSONDecodeError:
                                    arguments = {"_raw": tool_call.function.arguments}
                                
                                function_calls.append(AssistantFunctionCall(
                                    name=function_name,
                                    arguments=arguments
                                ))
                        
                        # Return function calls with thread and run info for submission
                        return AssistantResponse(
                            reply_text="",
                            function_calls=function_calls,
                            thread_id=thread_id,
                            run_id=run.id,
                            tool_call_ids=[tc.id for tc in tool_calls]
                        )
            
            if run.status == "completed":
                # Get messages
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                if messages.data:
                    latest_message = messages.data[0]
                    if latest_message.role == "assistant":
                        content = latest_message.content[0]
                        if hasattr(content, 'text'):
                            # Clear active run flag on completion
                            try:
                                redis_client.delete(active_run_key)
                            except Exception:
                                pass
                            return AssistantResponse(
                                reply_text=content.text.value,
                                function_calls=[]
                            )
            
            # Handle other statuses
            if run.status == "failed":
                error_msg = run.last_error.message if run.last_error else "Unknown error"
                print(f"Assistant run failed: {error_msg}")
            elif run.status == "cancelled":
                print(f"Assistant run was cancelled")
            elif run.status == "expired":
                print(f"Assistant run expired")
            # Clear flag on terminal state
            try:
                redis_client.delete(active_run_key)
            except Exception:
                pass
            
            return AssistantResponse(
                reply_text="Lo siento, no pude procesar tu mensaje en este momento.",
                function_calls=[]
            )
            
        except Exception as e:
            print(f"Error in assistant conversation: {e}")
            return AssistantResponse(
                reply_text="Lo siento, hubo un error al procesar tu mensaje.",
                function_calls=[]
            )

    def submit_tool_outputs_and_wait(
        self,
        thread_id: str,
        run_id: str,
        tool_outputs: List[Dict[str, str]],
        on_tool_calls: Optional[Any] = None,
    ) -> str:
        """Submit tool outputs to a run and wait for completion."""
        try:
            client = self._require_client()
            from ..extensions import redis_extension
            redis_client = redis_extension.client
            active_run_key = f"oa:thread:{thread_id}:active_run"
            
            # Submit tool outputs
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs
            )
            
            # Wait for completion
            import time
            max_iterations = 60
            iterations = 0
            
            while run.status in ["queued", "in_progress", "requires_action"] and iterations < max_iterations:
                iterations += 1
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_id
                )
                # Handle subsequent tool calls
                if run.status == "requires_action" and on_tool_calls is not None:
                    required_action = run.required_action
                    tool_calls = required_action.submit_tool_outputs.tool_calls if required_action else []
                    calls: List[AssistantFunctionCall] = []
                    call_ids: List[str] = []
                    for tc in tool_calls:
                        if tc.type == "function":
                            call_ids.append(tc.id)
                            try:
                                args = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                args = {"_raw": tc.function.arguments}
                            calls.append(AssistantFunctionCall(name=tc.function.name, arguments=args))
                    if calls:
                        try:
                            results: List[ToolResult] = on_tool_calls(calls)
                            # Align outputs by index
                            outputs_payload = []
                            for i, cid in enumerate(call_ids):
                                output_str = results[i].content if i < len(results) else "{}"
                                outputs_payload.append({"tool_call_id": cid, "output": output_str})
                            run = client.beta.threads.runs.submit_tool_outputs(
                                thread_id=thread_id,
                                run_id=run_id,
                                tool_outputs=outputs_payload,
                            )
                            continue
                        except Exception:
                            pass
            
            if run.status == "completed":
                # Get latest assistant message
                messages = client.beta.threads.messages.list(thread_id=thread_id, limit=1)
                if messages.data:
                    latest_message = messages.data[0]
                    if latest_message.role == "assistant":
                        content = latest_message.content[0]
                        if hasattr(content, 'text'):
                            try:
                                redis_client.delete(active_run_key)
                            except Exception:
                                pass
                            return content.text.value
            
            # Clear flag on terminal states as safety
            try:
                redis_client.delete(active_run_key)
            except Exception:
                pass
            return "Lo siento, no pude completar tu solicitud."
            
        except Exception as e:
            print(f"Error submitting tool outputs: {e}")
            return "Lo siento, hubo un error al procesar las acciones."

    def _get_or_create_thread(self, client, user_phone: str = None, namespace: str | None = None) -> str:
        """Get existing thread for user or create a new one.
        Namespace isolates threads per assistant/bot when provided.
        """
        try:
            # Usar redis_extension.client en vez de redis_client
            from ..extensions import redis_extension
            redis_client = redis_extension.client

            if not user_phone:
                # If no user phone, create a temporary thread
                thread = client.beta.threads.create()
                return thread.id

            # Use Redis to store thread_id per user (and namespace if provided)
            ns = namespace or "default"
            thread_key = f"thread:{ns}:{user_phone}"

            try:
                # Try to get existing thread
                thread_id = redis_client.get(thread_key)
                if thread_id:
                    # Handle both string and bytes from Redis
                    if isinstance(thread_id, bytes):
                        thread_id = thread_id.decode('utf-8')
                    # else: thread_id is already a string

                    # Verify thread still exists in OpenAI
                    try:
                        client.beta.threads.retrieve(thread_id)
                        return thread_id
                    except:
                        # Thread doesn't exist anymore, create new one
                        pass

                # Create new thread
                thread = client.beta.threads.create()
                thread_id = thread.id

                # Store in Redis with 7 days expiration
                redis_client.setex(thread_key, 604800, thread_id)  # 7 days

                return thread_id

            except Exception as redis_error:
                print(f"Redis error: {redis_error}")
                # If Redis fails, just create a new thread
                thread = client.beta.threads.create()
                return thread.id

        except Exception as e:
            print(f"Error managing thread for {user_phone}: {e}")
            # Fallback: create temporary thread
            thread = client.beta.threads.create()
            return thread.id
    
    def _parse_chat_response(self, response) -> AssistantResponse:
        """Parse regular chat completion response."""
        try:
            message = response.choices[0].message
            reply_text = message.content or "No pude generar una respuesta."
            
            function_calls = []
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function":
                        function_calls.append(AssistantFunctionCall(
                            name=tool_call.function.name,
                            arguments=json.loads(tool_call.function.arguments)
                        ))
            
            return AssistantResponse(
                reply_text=reply_text,
                function_calls=function_calls
            )
        except Exception as e:
            print(f"Error parsing chat response: {e}")
            return AssistantResponse(
                reply_text="Error al procesar la respuesta.",
                function_calls=[]
            )


# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------

def _safe_get_outputs(response: Any) -> List[Dict[str, Any]]:
    candidate = getattr(response, "output", None)
    if candidate is None and hasattr(response, "model_dump"):
        candidate = response.model_dump().get("output")
    if candidate is None and hasattr(response, "data"):
        candidate = response.data
    if candidate is None:
        return []

    items: List[Dict[str, Any]] = []
    for element in candidate:
        items.append(_safe_to_dict(element))
    return items


def _safe_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return {k: v for k, v in value.__dict__.items() if not k.startswith("_")}
    return {"value": value}


def _extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_extract_text_content(item) for item in content]
        return "".join(parts)
    if isinstance(content, dict):
        if "text" in content:
            return _extract_text_content(content["text"])
        if "value" in content:
            return _extract_text_content(content["value"])
        return "".join(_extract_text_content(v) for v in content.values())
    return str(content)
