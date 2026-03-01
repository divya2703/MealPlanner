"""Tests for seed data modules."""

from app.data.indian_meals import MEALS
from app.data.seasonal_ingredients import SEASONAL_VEGETABLES
from app.data.staple_ingredients import STAPLES


def test_meals_not_empty():
    assert len(MEALS) > 0


def test_meals_have_required_fields():
    for meal in MEALS:
        assert "name" in meal
        assert "meal_types" in meal
        assert "prep_time" in meal
        assert "complexity" in meal
        assert isinstance(meal["meal_types"], list)
        assert len(meal["meal_types"]) > 0


def test_meals_valid_types():
    valid_types = {"breakfast", "lunch", "dinner"}
    for meal in MEALS:
        for mt in meal["meal_types"]:
            assert mt in valid_types, f"{meal['name']} has invalid meal type: {mt}"


def test_meals_valid_complexity():
    valid = {"easy", "medium", "hard"}
    for meal in MEALS:
        assert meal["complexity"] in valid, f"{meal['name']} has invalid complexity"


def test_meals_unique_names():
    names = [m["name"] for m in MEALS]
    assert len(names) == len(set(names)), "Duplicate meal names found"


def test_has_all_meal_types():
    all_types = set()
    for meal in MEALS:
        all_types.update(meal["meal_types"])
    assert "breakfast" in all_types
    assert "lunch" in all_types
    assert "dinner" in all_types


def test_seasonal_vegetables_covers_all_months():
    for month in range(1, 13):
        assert month in SEASONAL_VEGETABLES
        assert len(SEASONAL_VEGETABLES[month]) > 0


def test_staples_not_empty():
    assert len(STAPLES) > 0


def test_staples_have_required_fields():
    for s in STAPLES:
        assert "name" in s
        assert "category" in s
        assert "unit" in s


def test_staples_valid_categories():
    valid = {"grain", "pulse", "spice", "dairy", "oil", "vegetable", "other"}
    for s in STAPLES:
        assert s["category"] in valid, f"{s['name']} has invalid category: {s['category']}"


def test_staples_unique_names():
    names = [s["name"] for s in STAPLES]
    assert len(names) == len(set(names)), "Duplicate staple names found"
