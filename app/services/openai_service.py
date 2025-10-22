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

        input_messages = self._build_messages(instructions, conversation)

        response = client.responses.create(
            model=model,
            input=input_messages,
            tools=list(tool_definitions or []),
        )

        return self._parse_response(response)

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
