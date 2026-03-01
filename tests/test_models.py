"""Tests for app.models — ORM model creation and properties."""

import json
from datetime import date, datetime

from app.models import (
    ConversationState,
    DailyPlan,
    GroceryList,
    GroceryListItem,
    Ingredient,
    Meal,
    MealHistory,
    MealIngredient,
    PantryItem,
    PlannedMeal,
    UserPreferences,
    WeeklyPlan,
)


def test_user_preferences_defaults(db):
    prefs = UserPreferences(user_id="whatsapp:+911234567890")
    db.add(prefs)
    db.commit()
    db.refresh(prefs)

    assert prefs.family_size == 3
    assert prefs.spice_level == "medium"
    assert prefs.cuisine_preference == "indian_vegetarian"
    assert prefs.max_prep_time_minutes == 60
    assert prefs.dislikes == []
    assert prefs.favorites == []


def test_user_preferences_json_properties(db):
    prefs = UserPreferences(
        user_id="whatsapp:+911234567890",
        dislikes_json=json.dumps(["bitter gourd", "karela"]),
        favorites_json=json.dumps(["paneer butter masala"]),
    )
    db.add(prefs)
    db.commit()
    db.refresh(prefs)

    assert prefs.dislikes == ["bitter gourd", "karela"]
    assert prefs.favorites == ["paneer butter masala"]


def test_meal_creation_and_properties(db):
    meal = Meal(
        name="Poha",
        meal_types_json=json.dumps(["breakfast"]),
        prep_time_minutes=15,
        complexity="easy",
        seasonal_months_json=json.dumps([]),
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)

    assert meal.name == "Poha"
    assert meal.meal_types == ["breakfast"]
    assert meal.seasonal_months == []
    assert meal.is_active is True


def test_meal_with_seasonal_months(db):
    meal = Meal(
        name="Aloo Gobi",
        seasonal_months_json=json.dumps([10, 11, 12, 1, 2]),
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)

    assert meal.seasonal_months == [10, 11, 12, 1, 2]


def test_ingredient_creation(db):
    ing = Ingredient(name="tomato", category="vegetable", unit="kg", is_staple=True, swiggy_search_term="tomato")
    db.add(ing)
    db.commit()
    db.refresh(ing)

    assert ing.name == "tomato"
    assert ing.is_staple is True
    assert ing.swiggy_search_term == "tomato"


def test_meal_ingredient_junction(db):
    meal = Meal(name="Dal Tadka")
    db.add(meal)
    ing = Ingredient(name="toor dal", category="pulse", unit="g")
    db.add(ing)
    db.flush()

    mi = MealIngredient(meal_id=meal.id, ingredient_id=ing.id, quantity_per_serving=50, unit="g")
    db.add(mi)
    db.commit()
    db.refresh(mi)

    assert mi.meal.name == "Dal Tadka"
    assert mi.ingredient.name == "toor dal"
    assert mi.quantity_per_serving == 50


def test_weekly_plan_hierarchy(db):
    wp = WeeklyPlan(week_start=date(2026, 3, 2), status="draft")
    db.add(wp)
    db.flush()

    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=date(2026, 3, 2))
    db.add(dp)
    db.flush()

    pm = PlannedMeal(daily_plan_id=dp.id, meal_type="breakfast", meal_name="Poha")
    db.add(pm)
    db.commit()
    db.refresh(wp)

    assert len(wp.daily_plans) == 1
    assert wp.daily_plans[0].planned_meals[0].meal_name == "Poha"
    assert wp.daily_plans[0].planned_meals[0].meal_type == "breakfast"


def test_meal_history(db):
    mh = MealHistory(meal_name="Rajma Chawal", meal_type="lunch", cooked_date=date(2026, 3, 1), rating=4)
    db.add(mh)
    db.commit()
    db.refresh(mh)

    assert mh.meal_name == "Rajma Chawal"
    assert mh.rating == 4


def test_pantry_item(db):
    pi = PantryItem(name="onion", quantity=2, unit="kg", low_threshold=0.5)
    db.add(pi)
    db.commit()
    db.refresh(pi)

    assert pi.quantity == 2
    assert pi.low_threshold == 0.5


def test_grocery_list_with_items(db):
    gl = GroceryList(status="pending")
    db.add(gl)
    db.flush()

    item = GroceryListItem(
        grocery_list_id=gl.id,
        ingredient_name="paneer",
        category="dairy",
        quantity=500,
        unit="g",
    )
    db.add(item)
    db.commit()
    db.refresh(gl)

    assert len(gl.items) == 1
    assert gl.items[0].ingredient_name == "paneer"
    assert gl.items[0].is_bought is False


def test_conversation_state_context(db):
    cs = ConversationState(
        user_id="whatsapp:+911234567890",
        flow_name="weekly_plan",
        step="awaiting_approval",
    )
    cs.context = {"plan_id": 42}
    db.add(cs)
    db.commit()
    db.refresh(cs)

    assert cs.context == {"plan_id": 42}
    assert cs.flow_name == "weekly_plan"
    assert cs.step == "awaiting_approval"


def test_weekly_plan_cascade_delete(db):
    wp = WeeklyPlan(week_start=date(2026, 3, 2))
    db.add(wp)
    db.flush()

    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=date(2026, 3, 2))
    db.add(dp)
    db.flush()

    pm = PlannedMeal(daily_plan_id=dp.id, meal_type="lunch", meal_name="Chole")
    db.add(pm)
    db.commit()

    db.delete(wp)
    db.commit()

    assert db.query(DailyPlan).count() == 0
    assert db.query(PlannedMeal).count() == 0
