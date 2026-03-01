"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import create_tables
from app.routers import health, telegram, whatsapp
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Meal Planning Bot...")
    create_tables()
    logger.info("Database tables created")
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    logger.info("Meal Planning Bot stopped")


app = FastAPI(title="Meal Planning WhatsApp Agent", lifespan=lifespan)

app.include_router(health.router)
app.include_router(whatsapp.router)
app.include_router(telegram.router)
