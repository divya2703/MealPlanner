"""Telegram webhook endpoint."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.whatsapp_bot import handle_message

router = APIRouter(prefix="/webhook", tags=["telegram"])
logger = logging.getLogger(__name__)


@router.post("/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive incoming Telegram updates."""
    data = await request.json()
    logger.info(f"Telegram update: {data.get('update_id')}")

    try:
        _process_update(db, data)
    except Exception:
        logger.exception("Error processing Telegram update")

    return {}


def _process_update(db: Session, data: dict):
    message = data.get("message") or data.get("edited_message")
    if not message:
        return

    text = message.get("text", "").strip()
    if not text:
        return

    chat = message["chat"]
    chat_id = chat["id"]
    chat_type = chat["type"]  # "private", "group", "supergroup"

    user_id = f"tg:{chat_id}"

    # Auto-register Telegram groups as households
    if chat_type in ("group", "supergroup"):
        _ensure_telegram_group(db, user_id, chat_id, chat.get("title", ""))

    # Strip /command@botname prefix
    if text.startswith("/"):
        text = text.lstrip("/").split("@")[0]

    handle_message(db, user_id, text)


def _ensure_telegram_group(db: Session, user_id: str, chat_id: int, group_title: str):
    """Auto-create a HouseholdGroup when bot is first used in a Telegram group."""
    from app.models import HouseholdGroup, UserPreferences

    prefs = db.query(UserPreferences).filter_by(user_id=user_id).first()
    if prefs and prefs.group_id:
        return

    group_slug = f"tg-{chat_id}"
    group = db.query(HouseholdGroup).filter_by(name=group_slug).first()
    if not group:
        group = HouseholdGroup(name=group_slug)
        db.add(group)
        db.flush()

    if not prefs:
        prefs = UserPreferences(user_id=user_id, group_id=group.id)
        db.add(prefs)
    else:
        prefs.group_id = group.id

    db.commit()
    logger.info(f"Auto-registered Telegram group {chat_id} as household {group_slug}")
