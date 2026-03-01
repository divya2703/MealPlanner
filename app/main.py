"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import create_tables
from app.routers import api, health, telegram, whatsapp
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Meal Planning Bot...")
    create_tables()
    logger.info("Database tables created")
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Meal Planning Bot stopped")


app = FastAPI(title="Meal Planning WhatsApp Agent", lifespan=lifespan)

app.include_router(health.router)
app.include_router(whatsapp.router)
app.include_router(telegram.router)
app.include_router(api.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/dashboard")
async def dashboard():
    return FileResponse(str(STATIC_DIR / "dashboard.html"))
