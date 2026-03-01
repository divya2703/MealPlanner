"""Tests for app.services.meal_planner — formatting functions and helpers."""

from datetime import date

from app.models import DailyPlan, MealHistory, PlannedMeal, UserPreferences, WeeklyPlan
from app.services.meal_planner import (
    _get_recent_meals,
    _get_user_prefs,
    format_daily_meals,
    format_weekly_plan,
)


def test_get_user_prefs_creates_default(db):
    prefs = _get_user_prefs(db)
    assert prefs is not None
    assert prefs.family_size == 3
    assert prefs.spice_level == "medium"


def test_get_user_prefs_returns_existing(db):
    existing = UserPreferences(user_id="whatsapp:+91999", family_size=5, spice_level="spicy")
    db.add(existing)
    db.commit()

    prefs = _get_user_prefs(db)
    assert prefs.family_size == 5
    assert prefs.spice_level == "spicy"


def test_get_recent_meals_empty(db):
    result = _get_recent_meals(db)
    assert result == []


def test_get_recent_meals(db):
    mh1 = MealHistory(meal_name="Poha", meal_type="breakfast", cooked_date=date.today())
    mh2 = MealHistory(meal_name="Dal Rice", meal_type="lunch", cooked_date=date.today())
    db.add_all([mh1, mh2])
    db.commit()

    result = _get_recent_meals(db)
    assert set(result) == {"Poha", "Dal Rice"}


def test_get_recent_meals_excludes_old(db):
    from datetime import timedelta
    old_date = date.today() - timedelta(days=30)
    mh = MealHistory(meal_name="Old Dish", meal_type="dinner", cooked_date=old_date)
    db.add(mh)
    db.commit()

    result = _get_recent_meals(db)
    assert result == []


def test_format_weekly_plan(db):
    wp = WeeklyPlan(week_start=date(2026, 3, 2))
    db.add(wp)
    db.flush()

    for i, day_date in enumerate([date(2026, 3, 2), date(2026, 3, 3)]):
        dp = DailyPlan(weekly_plan_id=wp.id, plan_date=day_date)
        db.add(dp)
        db.flush()
        for mt, name in [("breakfast", "Poha"), ("lunch", "Dal Rice"), ("dinner", "Roti Sabzi")]:
            pm = PlannedMeal(daily_plan_id=dp.id, meal_type=mt, meal_name=name)
            db.add(pm)

    db.commit()
    db.refresh(wp)

    result = format_weekly_plan(wp)
    assert "*Weekly Meal Plan*" in result
    assert "Monday" in result
    assert "Tuesday" in result
    assert "Poha" in result
    assert "Dal Rice" in result
    assert "Breakfast" in result
    assert "Lunch" in result
    assert "Dinner" in result


def test_format_daily_meals(db):
    wp = WeeklyPlan(week_start=date(2026, 3, 2))
    db.add(wp)
    db.flush()

    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=date(2026, 3, 2))
    db.add(dp)
    db.flush()

    for mt, name in [("breakfast", "Idli"), ("lunch", "Sambar Rice"), ("dinner", "Chapati Sabzi")]:
        db.add(PlannedMeal(daily_plan_id=dp.id, meal_type=mt, meal_name=name))
    db.commit()
    db.refresh(dp)

    result = format_daily_meals(dp)
    assert "Monday" in result
    assert "Idli" in result
    assert "Sambar Rice" in result
    assert "Chapati Sabzi" in result
    assert "Breakfast" in result
