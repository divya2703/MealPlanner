"""Twilio WhatsApp webhook endpoint."""

import logging

from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.whatsapp_bot import handle_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])


@router.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(""),
    From: str = Form(""),
    db: Session = Depends(get_db),
):
    """Receive incoming WhatsApp messages from Twilio.

    Twilio expects an empty TwiML response (we reply via the API instead).
    """
    logger.info(f"WhatsApp message from {From}: {Body}")

    if Body and From:
        try:
            handle_message(db, From, Body)
        except Exception:
            logger.exception(f"Error handling message from {From}")

    # Return empty TwiML — we send replies via the REST API
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )
