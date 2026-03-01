"""Twilio WhatsApp webhook endpoint."""

import logging
import traceback

from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BotLog
from app.services.whatsapp_bot import handle_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])


@router.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(""),
    From: str = Form(""),
    db: Session = Depends(get_db),
):
    """Receive incoming WhatsApp messages from Twilio."""
    logger.info(f"WhatsApp message from {From}: {Body}")

    if Body and From:
        # Log inbound (best-effort)
        try:
            db.add(BotLog(direction="inbound", user_id=From, message=Body))
            db.commit()
        except Exception:
            db.rollback()

        try:
            handle_message(db, From, Body)
        except Exception:
            error_str = traceback.format_exc()
            logger.exception(f"Error handling message from {From}")
            try:
                db.add(BotLog(direction="error", user_id=From, message=Body, error=error_str))
                db.commit()
            except Exception:
                db.rollback()
    else:
        logger.warning(f"Empty webhook: Body={Body!r}, From={From!r}")

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
