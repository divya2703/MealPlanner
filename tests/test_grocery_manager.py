"""Tests for app.services.grocery_manager — pantry, grocery list formatting."""

from datetime import date, timedelta

from app.models import (
    DailyPlan,
    GroceryList,
    GroceryListItem,
    PantryItem,
    PlannedMeal,
    WeeklyPlan,
)
from app.services.grocery_manager import (
    format_grocery_list,
    format_swiggy_list,
    get_current_grocery_list,
    get_low_stock_items,
    get_today_meals,
    get_tomorrow_meals,
    mark_depleted,
    mark_items_bought,
    update_pantry,
)


def _make_grocery_list(db, items_data):
    gl = GroceryList(status="pending")
    db.add(gl)
    db.flush()
    for item in items_data:
        gli = GroceryListItem(grocery_list_id=gl.id, **item)
        db.add(gli)
    db.commit()
    db.refresh(gl)
    return gl


def test_format_grocery_list_groups_by_category(db):
    gl = _make_grocery_list(db, [
        {"ingredient_name": "tomato", "category": "vegetable", "quantity": 1, "unit": "kg"},
        {"ingredient_name": "paneer", "category": "dairy", "quantity": 500, "unit": "g"},
        {"ingredient_name": "rice", "category": "grain", "quantity": 2, "unit": "kg"},
    ])

    result = format_grocery_list(gl)
    assert "*Grocery List*" in result
    assert "tomato" in result
    assert "paneer" in result
    assert "rice" in result
    # Categories should appear as headers
    assert "*Vegetable*" in result
    assert "*Dairy*" in result
    assert "*Grain*" in result


def test_format_grocery_list_shows_bought_status(db):
    gl = _make_grocery_list(db, [
        {"ingredient_name": "onion", "category": "vegetable", "quantity": 2, "unit": "kg", "is_bought": True},
        {"ingredient_name": "potato", "category": "vegetable", "quantity": 1, "unit": "kg", "is_bought": False},
    ])

    result = format_grocery_list(gl)
    assert "✅" in result  # bought item
    assert "⬜" in result  # unbought item


def test_format_swiggy_list(db):
    gl = _make_grocery_list(db, [
        {"ingredient_name": "paneer", "category": "dairy", "quantity": 500, "unit": "g", "swiggy_search_term": "paneer"},
    ])

    result = format_swiggy_list(gl)
    assert "Swiggy Instamart" in result
    assert "paneer" in result
    assert "swiggy.com" in result


def test_format_swiggy_list_excludes_bought(db):
    gl = _make_grocery_list(db, [
        {"ingredient_name": "onion", "category": "vegetable", "quantity": 1, "unit": "kg", "is_bought": True},
        {"ingredient_name": "tomato", "category": "vegetable", "quantity": 1, "unit": "kg", "is_bought": False},
    ])

    result = format_swiggy_list(gl)
    assert "tomato" in result
    assert "onion" not in result


def test_mark_items_bought(db):
    gl = _make_grocery_list(db, [
        {"ingredient_name": "tomato", "category": "vegetable", "quantity": 1, "unit": "kg"},
        {"ingredient_name": "onion", "category": "vegetable", "quantity": 2, "unit": "kg"},
        {"ingredient_name": "paneer", "category": "dairy", "quantity": 500, "unit": "g"},
    ])

    matched = mark_items_bought(db, gl, ["tomato", "paneer"])
    assert "tomato" in matched
    assert "paneer" in matched
    assert "onion" not in matched

    db.refresh(gl)
    for item in gl.items:
        if item.ingredient_name in ("tomato", "paneer"):
            assert item.is_bought is True
        else:
            assert item.is_bought is False


def test_mark_items_bought_partial_match(db):
    gl = _make_grocery_list(db, [
        {"ingredient_name": "green chilli", "category": "vegetable", "quantity": 10, "unit": "pieces"},
    ])

    matched = mark_items_bought(db, gl, ["chilli"])
    assert "green chilli" in matched


def test_update_pantry_creates_new(db):
    result = update_pantry(db, "tomato", 2, "kg")
    assert result.name == "tomato"
    assert result.quantity == 2
    assert result.unit == "kg"


def test_update_pantry_updates_existing(db):
    update_pantry(db, "tomato", 2, "kg")
    result = update_pantry(db, "tomato", 5, "kg")
    assert result.quantity == 5
    assert db.query(PantryItem).filter(PantryItem.name.ilike("%tomato%")).count() == 1


def test_mark_depleted(db):
    update_pantry(db, "onion", 3, "kg")
    result = mark_depleted(db, "onion")
    assert result is not None
    assert result.quantity == 0


def test_mark_depleted_nonexistent(db):
    result = mark_depleted(db, "nonexistent_item")
    assert result is None


def test_get_low_stock_items(db):
    pi = PantryItem(name="oil", quantity=0.1, unit="l", low_threshold=0.5)
    db.add(pi)
    pi2 = PantryItem(name="rice", quantity=5, unit="kg", low_threshold=1)
    db.add(pi2)
    db.commit()

    low = get_low_stock_items(db)
    assert len(low) == 1
    assert low[0].name == "oil"


def test_get_current_grocery_list(db):
    gl1 = GroceryList(status="completed")
    gl2 = GroceryList(status="pending")
    db.add_all([gl1, gl2])
    db.commit()

    result = get_current_grocery_list(db)
    assert result is not None
    assert result.status == "pending"


def test_get_current_grocery_list_none(db):
    result = get_current_grocery_list(db)
    assert result is None


def test_get_today_meals(db):
    today = date.today()
    wp = WeeklyPlan(week_start=today)
    db.add(wp)
    db.flush()

    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=today)
    db.add(dp)
    db.flush()

    pm = PlannedMeal(daily_plan_id=dp.id, meal_type="breakfast", meal_name="Poha")
    db.add(pm)
    db.commit()

    meals = get_today_meals(db)
    assert len(meals) == 1
    assert meals[0].meal_name == "Poha"


def test_get_today_meals_empty(db):
    meals = get_today_meals(db)
    assert meals == []


def test_get_tomorrow_meals(db):
    tomorrow = date.today() + timedelta(days=1)
    wp = WeeklyPlan(week_start=tomorrow)
    db.add(wp)
    db.flush()

    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=tomorrow)
    db.add(dp)
    db.flush()

    pm = PlannedMeal(daily_plan_id=dp.id, meal_type="lunch", meal_name="Dal Rice")
    db.add(pm)
    db.commit()

    meals = get_tomorrow_meals(db)
    assert len(meals) == 1
    assert meals[0].meal_name == "Dal Rice"
