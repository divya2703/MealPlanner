"""Twilio outbound WhatsApp messaging with message splitting."""

import logging

from twilio.rest import Client

from app.config import settings

logger = logging.getLogger(__name__)

# WhatsApp message limit is 1600 characters
MAX_WHATSAPP_LENGTH = 1500

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def split_message(text: str, max_length: int = MAX_WHATSAPP_LENGTH) -> list[str]:
    """Split a long message into chunks that fit WhatsApp limits.

    Tries to split on double-newlines (paragraph boundaries) first,
    then single newlines, then by character limit.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to find a good split point
        split_at = max_length

        # Prefer splitting at double newline
        double_nl = remaining.rfind("\n\n", 0, max_length)
        if double_nl > max_length // 2:
            split_at = double_nl + 2
        else:
            # Try single newline
            single_nl = remaining.rfind("\n", 0, max_length)
            if single_nl > max_length // 2:
                split_at = single_nl + 1

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks


def send_whatsapp(to: str, body: str) -> bool:
    """Send a WhatsApp message, splitting if necessary.

    Args:
        to: WhatsApp number in format 'whatsapp:+91XXXXXXXXXX'
        body: Message text

    Returns:
        True if all message parts were sent successfully.
    """
    client = _get_client()
    parts = split_message(body)

    for i, part in enumerate(parts):
        try:
            if len(parts) > 1:
                part = f"({i + 1}/{len(parts)})\n{part}" if i > 0 else part

            message = client.messages.create(
                from_=settings.twilio_whatsapp_from,
                body=part,
                to=to,
            )
            logger.info(f"Sent WhatsApp message {message.sid} to {to} (part {i + 1}/{len(parts)})")
        except Exception:
            logger.exception(f"Failed to send WhatsApp message to {to}")
            return False

    return True


def send_to_user(body: str) -> bool:
    """Send a WhatsApp message to the configured user."""
    return send_whatsapp(settings.user_whatsapp_number, body)
