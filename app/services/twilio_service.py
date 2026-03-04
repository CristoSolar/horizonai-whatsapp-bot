"""Helpers for interacting with Twilio's WhatsApp API."""
from __future__ import annotations

from typing import Optional

from flask import current_app

try:
    from twilio.rest import Client as TwilioClient  # type: ignore
except Exception:  # pragma: no cover
    TwilioClient = None  # type: ignore

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
        messaging_service_sid: Optional[str] = None,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> Optional[str]:
        client = self._resolve_client(
            twilio_account_sid=twilio_account_sid,
            twilio_auth_token=twilio_auth_token,
        )
        destination = self._format_whatsapp_number(to_number)

        params = {
            "to": destination,
            "body": body,
            "media_url": media_url,
        }
        if messaging_service_sid:
            params["messaging_service_sid"] = messaging_service_sid
        else:
            outbound = self._format_whatsapp_number(
                from_number or current_app.config.get("TWILIO_WHATSAPP_FROM")
            )
            params["from_"] = outbound

        message = client.messages.create(**params)
        return getattr(message, "sid", None)

    def send_whatsapp_template(
        self,
        *,
        to_number: str,
        content_sid: str,
        content_variables: Optional[dict] = None,
        from_number: Optional[str] = None,
        messaging_service_sid: Optional[str] = None,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
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
        
        client = self._resolve_client(
            twilio_account_sid=twilio_account_sid,
            twilio_auth_token=twilio_auth_token,
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

    def _resolve_client(
        self,
        *,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
    ):
        if twilio_account_sid and not twilio_auth_token:
            raise RuntimeError(
                "Bot Twilio config is incomplete: twilio_account_sid is set but twilio_auth_token is missing. "
                "Set metadata.twilio_auth_token or metadata.twilio_auth_token_ref."
            )

        if twilio_auth_token and not twilio_account_sid:
            raise RuntimeError(
                "Bot Twilio config is incomplete: twilio_auth_token is set but twilio_account_sid is missing."
            )

        if twilio_account_sid and twilio_auth_token:
            if TwilioClient is None:
                raise RuntimeError("twilio package is not available in runtime")
            return TwilioClient(twilio_account_sid, twilio_auth_token)

        client = self._extension.client
        if client is None:
            raise RuntimeError(
                "Twilio client is not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
            )
        return client

    @staticmethod
    def _format_whatsapp_number(number: Optional[str]) -> str:
        if not number:
            raise RuntimeError("WhatsApp number is required")
        if number.startswith("whatsapp:"):
            return number
        return f"whatsapp:{number}"
