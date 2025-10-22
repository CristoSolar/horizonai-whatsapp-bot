"""Helpers for interacting with Twilio's WhatsApp API."""
from __future__ import annotations

from typing import Optional

from flask import current_app

from ..extensions import TwilioExtension


class TwilioMessagingService:
    def __init__(self, extension: TwilioExtension) -> None:
        self._extension = extension

    def send_whatsapp_message(
        self,
        *,
        to_number: str,
        body: str,
        from_number: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> Optional[str]:
        client = self._extension.client
        if client is None:
            raise RuntimeError(
                "Twilio client is not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
            )

        outbound = self._format_whatsapp_number(
            from_number or current_app.config.get("TWILIO_WHATSAPP_FROM")
        )
        destination = self._format_whatsapp_number(to_number)

        message = client.messages.create(
            from_=outbound,
            to=destination,
            body=body,
            media_url=media_url,
        )
        return getattr(message, "sid", None)

    @staticmethod
    def _format_whatsapp_number(number: Optional[str]) -> str:
        if not number:
            raise RuntimeError("WhatsApp number is required")
        if number.startswith("whatsapp:"):
            return number
        return f"whatsapp:{number}"
