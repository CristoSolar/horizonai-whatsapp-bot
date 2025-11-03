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

    def send_whatsapp_template(
        self,
        *,
        to_number: str,
        content_sid: str,
        content_variables: Optional[dict] = None,
        from_number: Optional[str] = None,
        messaging_service_sid: Optional[str] = None,
    ) -> Optional[str]:
        """Send WhatsApp message using an approved Content Template.
        
        Args:
            to_number: Destination WhatsApp number
            content_sid: The SID of the approved Content Template (starts with HX)
            content_variables: Dictionary of variables for the template (e.g., {"1": "Name", "2": "Value"})
            from_number: Sender WhatsApp number (optional if using messaging_service_sid)
            messaging_service_sid: Messaging Service SID (optional)
        
        Returns:
            Message SID if successful, None otherwise
        """
        import json
        
        client = self._extension.client
        if client is None:
            raise RuntimeError(
                "Twilio client is not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
            )

        destination = self._format_whatsapp_number(to_number)
        
        params = {
            "content_sid": content_sid,
            "to": destination,
        }
        
        # Add from number or messaging service
        if messaging_service_sid:
            params["messaging_service_sid"] = messaging_service_sid
        else:
            outbound = self._format_whatsapp_number(
                from_number or current_app.config.get("TWILIO_WHATSAPP_FROM")
            )
            params["from_"] = outbound
        
        # Add variables if provided
        if content_variables:
            params["content_variables"] = json.dumps(content_variables)
        
        message = client.messages.create(**params)
        return getattr(message, "sid", None)

    @staticmethod
    def _format_whatsapp_number(number: Optional[str]) -> str:
        if not number:
            raise RuntimeError("WhatsApp number is required")
        if number.startswith("whatsapp:"):
            return number
        return f"whatsapp:{number}"
