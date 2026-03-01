"""Scheduled jobs — weekly plan prompt, daily confirmation, morning summary."""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.models import DailyPlan, WeeklyPlan
from app.services.meal_planner import format_daily_meals
from app.services.message_sender import send_to_user
from app.services.whatsapp_bot import send_daily_confirmation

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def weekly_plan_reminder():
    """Sunday 9 AM — Remind user to generate weekly plan."""
    logger.info("Sending weekly plan reminder")
    send_to_user(
        "Good morning! ☀️ Time to plan meals for the week.\n\n"
        "Reply *plan* to generate a new weekly meal plan."
    )


def daily_confirmation():
    """Daily 8 PM — Send tomorrow's meals for confirmation."""
    logger.info("Sending daily confirmation")
    db = SessionLocal()
    try:
        send_daily_confirmation(db, settings.user_whatsapp_number)
    finally:
        db.close()


def morning_summary():
    """Daily 7 AM — Send today's finalized meals."""
    logger.info("Sending morning summary")
    db = SessionLocal()
    try:
        today = date.today()
        daily = db.query(DailyPlan).filter(DailyPlan.plan_date == today).first()
        if not daily:
            return

        formatted = format_daily_meals(daily)
        send_to_user(f"Good morning! ☀️ Here's today's menu:\n\n{formatted}")
    finally:
        db.close()


def low_stock_alert():
    """Weekly check for low pantry stock."""
    from app.services.grocery_manager import get_low_stock_items

    logger.info("Checking low stock items")
    db = SessionLocal()
    try:
        low_items = get_low_stock_items(db)
        if low_items:
            lines = ["*Low Stock Alert* ⚠️\n"]
            for item in low_items:
                qty = f"{item.quantity:g}" if item.quantity == int(item.quantity) else f"{item.quantity:.1f}"
                lines.append(f"• {item.name}: {qty} {item.unit}")
            lines.append("\nReply *out of [item]* to mark as depleted.")
            send_to_user("\n".join(lines))
    finally:
        db.close()


def start_scheduler():
    """Configure and start all scheduled jobs."""
    # Sunday 9 AM — weekly plan reminder
    scheduler.add_job(weekly_plan_reminder, "cron", day_of_week="sun", hour=9, minute=0, id="weekly_reminder")

    # Daily 8 PM — confirm tomorrow's meals
    scheduler.add_job(daily_confirmation, "cron", hour=20, minute=0, id="daily_confirmation")

    # Daily 7 AM — morning summary
    scheduler.add_job(morning_summary, "cron", hour=7, minute=0, id="morning_summary")

    # Wednesday 10 AM — mid-week low stock check
    scheduler.add_job(low_stock_alert, "cron", day_of_week="wed", hour=10, minute=0, id="low_stock_alert")

    scheduler.start()
    logger.info("Scheduler started with all jobs")


def stop_scheduler():
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
