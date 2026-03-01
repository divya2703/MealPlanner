"""REST API endpoints for the dashboard — meal history, calorie stats."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyPlan, MealHistory, PlannedMeal, UserPreferences, WeeklyPlan

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/meals/today")
def get_today_meals(group_id: int | None = None, db: Session = Depends(get_db)):
    """Get today's planned meals with calories."""
    today = date.today()
    q = db.query(DailyPlan)
    if group_id is not None:
        q = q.join(WeeklyPlan).filter(WeeklyPlan.group_id == group_id)
    daily = q.filter(DailyPlan.plan_date == today).first()
    if not daily:
        return {"date": str(today), "meals": [], "total_calories": 0}

    meals = []
    total = 0
    for pm in sorted(daily.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type)):
        meals.append({
            "meal_type": pm.meal_type,
            "meal_name": pm.meal_name,
            "calories": pm.estimated_calories or 0,
            "status": pm.status,
        })
        total += pm.estimated_calories or 0

    return {"date": str(today), "meals": meals, "total_calories": total}


@router.get("/meals/week")
def get_week_meals(group_id: int | None = None, db: Session = Depends(get_db)):
    """Get the current week's plan with calories per day."""
    q = db.query(WeeklyPlan).filter(WeeklyPlan.status.in_(["draft", "approved", "active"]))
    if group_id is not None:
        q = q.filter(WeeklyPlan.group_id == group_id)
    plan = q.order_by(WeeklyPlan.created_at.desc()).first()
    if not plan:
        return {"days": []}

    days = []
    for daily in sorted(plan.daily_plans, key=lambda d: d.plan_date):
        day_meals = []
        day_total = 0
        for pm in sorted(daily.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type)):
            day_meals.append({
                "meal_type": pm.meal_type,
                "meal_name": pm.meal_name,
                "calories": pm.estimated_calories or 0,
            })
            day_total += pm.estimated_calories or 0
        days.append({
            "date": str(daily.plan_date),
            "day_name": daily.plan_date.strftime("%A"),
            "meals": day_meals,
            "total_calories": day_total,
        })

    return {"days": days}


@router.get("/stats/calories")
def get_calorie_stats(
    days: int = Query(default=14, ge=1, le=90),
    group_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Get daily calorie totals for the last N days (for charting)."""
    start_date = date.today() - timedelta(days=days - 1)

    q = (
        db.query(DailyPlan)
        .join(WeeklyPlan)
        .filter(DailyPlan.plan_date >= start_date)
    )
    if group_id is not None:
        q = q.filter(WeeklyPlan.group_id == group_id)

    daily_plans = q.order_by(DailyPlan.plan_date).all()

    result = []
    for dp in daily_plans:
        day_total = sum(pm.estimated_calories or 0 for pm in dp.planned_meals)
        result.append({
            "date": str(dp.plan_date),
            "day_name": dp.plan_date.strftime("%a"),
            "total_calories": day_total,
            "meals": {
                pm.meal_type: pm.estimated_calories or 0
                for pm in dp.planned_meals
            },
        })

    return {"data": result}


@router.get("/stats/history")
def get_meal_history(
    days: int = Query(default=30, ge=1, le=90),
    group_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Get meal history with ratings."""
    cutoff = date.today() - timedelta(days=days)
    q = db.query(MealHistory).filter(MealHistory.cooked_date >= cutoff)
    if group_id is not None:
        q = q.filter(MealHistory.group_id == group_id)

    history = q.order_by(MealHistory.cooked_date.desc()).all()
    return {
        "history": [
            {
                "meal_name": h.meal_name,
                "meal_type": h.meal_type,
                "date": str(h.cooked_date),
                "rating": h.rating,
            }
            for h in history
        ]
    }


@router.get("/members")
def get_members(group_id: int | None = None, db: Session = Depends(get_db)):
    """Get household group members."""
    q = db.query(UserPreferences)
    if group_id is not None:
        q = q.filter(UserPreferences.group_id == group_id)

    members = q.all()
    return {
        "members": [
            {
                "name": m.display_name,
                "favorites": m.favorites,
                "dislikes": m.dislikes,
                "away_from": str(m.away_from) if m.away_from else None,
                "away_until": str(m.away_until) if m.away_until else None,
            }
            for m in members
        ]
    }
