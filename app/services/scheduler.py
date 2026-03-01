"""Scheduled jobs — weekly plan prompt, daily confirmation, morning summary."""

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models import DailyPlan, UserPreferences, WeeklyPlan
from app.services.meal_planner import format_daily_meals
from app.services.message_sender import send_message
from app.services.whatsapp_bot import send_daily_confirmation

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _get_all_group_members() -> dict[int, list[str]]:
    """Returns {group_id: [user_id, ...]} for all groups."""
    db = SessionLocal()
    try:
        users = db.query(UserPreferences).filter(UserPreferences.group_id.isnot(None)).all()
        groups: dict[int, list[str]] = {}
        for u in users:
            groups.setdefault(u.group_id, []).append(u.user_id)
        return groups
    finally:
        db.close()


def weekly_plan_reminder():
    """Sunday 9 AM — Remind users to generate weekly plan."""
    logger.info("Sending weekly plan reminder")
    for gid, members in _get_all_group_members().items():
        for user_id in members:
            send_message(user_id, "Good morning! ☀️ Time to plan meals for the week.\n\nReply *plan* to generate a new weekly meal plan.")


def daily_confirmation():
    """Daily 8 PM — Send tomorrow's meals for confirmation."""
    logger.info("Sending daily confirmation")
    db = SessionLocal()
    try:
        for gid, members in _get_all_group_members().items():
            for user_id in members:
                send_daily_confirmation(db, user_id, gid=gid)
    finally:
        db.close()


def morning_summary():
    """Daily 7 AM — Send today's finalized meals."""
    logger.info("Sending morning summary")
    db = SessionLocal()
    try:
        today = date.today()
        for gid, members in _get_all_group_members().items():
            daily = (
                db.query(DailyPlan)
                .join(WeeklyPlan)
                .filter(DailyPlan.plan_date == today, WeeklyPlan.group_id == gid)
                .first()
            )
            if not daily:
                continue

            formatted = format_daily_meals(daily)
            for user_id in members:
                send_message(user_id, f"Good morning! ☀️ Here's today's menu:\n\n{formatted}")
    finally:
        db.close()


def low_stock_alert():
    """Weekly check for low pantry stock."""
    from app.services.grocery_manager import get_low_stock_items

    logger.info("Checking low stock items")
    db = SessionLocal()
    try:
        for gid, members in _get_all_group_members().items():
            low_items = get_low_stock_items(db, group_id=gid)
            if low_items:
                lines = ["*Low Stock Alert* ⚠️\n"]
                for item in low_items:
                    qty = f"{item.quantity:g}" if item.quantity == int(item.quantity) else f"{item.quantity:.1f}"
                    lines.append(f"• {item.name}: {qty} {item.unit}")
                lines.append("\nReply *out of [item]* to mark as depleted.")
                msg = "\n".join(lines)
                for user_id in members:
                    send_message(user_id, msg)
    finally:
        db.close()


def start_scheduler():
    """Configure and start all scheduled jobs."""
    scheduler.add_job(weekly_plan_reminder, "cron", day_of_week="sun", hour=9, minute=0, id="weekly_reminder")
    scheduler.add_job(daily_confirmation, "cron", hour=20, minute=0, id="daily_confirmation")
    scheduler.add_job(morning_summary, "cron", hour=7, minute=0, id="morning_summary")
    scheduler.add_job(low_stock_alert, "cron", day_of_week="wed", hour=10, minute=0, id="low_stock_alert")

    scheduler.start()
    logger.info("Scheduler started with all jobs")


def stop_scheduler():
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
