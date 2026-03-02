"""Multi-platform outbound messaging with message splitting."""

import logging

from twilio.rest import Client

from app.config import settings

logger = logging.getLogger(__name__)

MAX_WHATSAPP_LENGTH = 1500
MAX_TELEGRAM_LENGTH = 4096

_twilio_client: Client | None = None


def _get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _twilio_client


def split_message(text: str, max_length: int = MAX_WHATSAPP_LENGTH) -> list[str]:
    """Split a long message into chunks.

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

        split_at = max_length

        double_nl = remaining.rfind("\n\n", 0, max_length)
        if double_nl > max_length // 2:
            split_at = double_nl + 2
        else:
            single_nl = remaining.rfind("\n", 0, max_length)
            if single_nl > max_length // 2:
                split_at = single_nl + 1

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks


def send_message(user_id: str, body: str) -> bool:
    """Unified send — dispatches to WhatsApp or Telegram based on user_id prefix."""
    _log_outbound(user_id, body)
    if user_id.startswith("tg:"):
        chat_id = user_id.removeprefix("tg:")
        return _send_telegram(chat_id, body)
    else:
        return _send_whatsapp(user_id, body)


def _log_outbound(user_id: str, body: str):
    """Log outbound message to DB (best-effort, never fails the send)."""
    try:
        from app.database import SessionLocal
        from app.models import BotLog
        db = SessionLocal()
        try:
            preview = body[:200] + "..." if len(body) > 200 else body
            db.add(BotLog(direction="outbound", user_id=user_id, message=preview))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass  # Never let logging break message sending


def _send_whatsapp(to: str, body: str) -> bool:
    """Send a WhatsApp message via Twilio, splitting if necessary."""
    client = _get_twilio_client()
    parts = split_message(body)

    for i, part in enumerate(parts):
        try:
            if len(parts) > 1 and i > 0:
                part = f"({i + 1}/{len(parts)})\n{part}"

            message = client.messages.create(
                from_=settings.twilio_whatsapp_from,
                body=part,
                to=to,
            )
            logger.info(f"Sent WhatsApp {message.sid} status={message.status} to={to}")
            _log_delivery(to, f"sid={message.sid} status={message.status}")
        except Exception as e:
            logger.exception(f"Failed to send WhatsApp message to {to}")
            _log_delivery(to, f"FAILED: {e}")
            return False

    return True


def _log_delivery(user_id: str, detail: str):
    """Log Twilio delivery status to DB."""
    try:
        from app.database import SessionLocal
        from app.models import BotLog
        db = SessionLocal()
        try:
            db.add(BotLog(direction="delivery", user_id=user_id, message=detail))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


def _send_telegram(chat_id: str, body: str) -> bool:
    """Send a Telegram message, splitting if necessary."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping message")
        return False

    import httpx

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    parts = split_message(body, max_length=MAX_TELEGRAM_LENGTH)

    for i, part in enumerate(parts):
        try:
            if len(parts) > 1 and i > 0:
                part = f"({i + 1}/{len(parts)})\n{part}"

            resp = httpx.post(url, json={"chat_id": int(chat_id), "text": part, "parse_mode": "Markdown"})
            if resp.status_code == 200:
                logger.info(f"Sent Telegram message to {chat_id} (part {i + 1}/{len(parts)})")
            else:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
        except Exception:
            logger.exception(f"Failed to send Telegram message to {chat_id}")
            return False

    return True


# Backwards-compatible alias
send_whatsapp = send_message
