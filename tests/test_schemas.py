"""Tests for app.schemas — Pydantic schema validation."""

from datetime import date

from app.schemas import (
    ClaudeGroceryExtract,
    ClaudeMealPlan,
    ClaudeSwapSuggestions,
    DailyPlanSchema,
    GroceryItemSchema,
    GroceryListSchema,
    PlannedMealSchema,
    SwapSuggestion,
    WeeklyPlanSchema,
)


def test_planned_meal_schema():
    pm = PlannedMealSchema(meal_type="breakfast", meal_name="Poha")
    assert pm.meal_type == "breakfast"
    assert pm.meal_name == "Poha"


def test_daily_plan_schema():
    dp = DailyPlanSchema(
        day="monday",
        date=date(2026, 3, 2),
        meals=[PlannedMealSchema(meal_type="breakfast", meal_name="Idli")],
    )
    assert dp.day == "monday"
    assert len(dp.meals) == 1


def test_weekly_plan_schema():
    wp = WeeklyPlanSchema(
        week_start=date(2026, 3, 2),
        days=[
            DailyPlanSchema(
                day="monday",
                date=date(2026, 3, 2),
                meals=[PlannedMealSchema(meal_type="lunch", meal_name="Dal Rice")],
            )
        ],
    )
    assert wp.week_start == date(2026, 3, 2)
    assert len(wp.days) == 1


def test_swap_suggestion():
    ss = SwapSuggestion(meal_name="Paneer Tikka", reason="Seasonal and quick")
    assert ss.meal_name == "Paneer Tikka"


def test_grocery_item_schema():
    gi = GroceryItemSchema(name="tomato", quantity=1.5, unit="kg", category="vegetable")
    assert gi.swiggy_search_term is None


def test_grocery_list_schema():
    gl = GroceryListSchema(
        items=[GroceryItemSchema(name="onion", quantity=2, unit="kg", category="vegetable")]
    )
    assert len(gl.items) == 1


def test_claude_meal_plan():
    plan = ClaudeMealPlan(
        days=[
            ClaudeMealPlan.DayPlan(day="monday", breakfast="Poha", lunch="Dal Rice", dinner="Roti Sabzi"),
        ]
    )
    assert plan.days[0].day == "monday"
    assert plan.days[0].breakfast == "Poha"


def test_claude_swap_suggestions():
    ss = ClaudeSwapSuggestions(
        suggestions=[
            ClaudeSwapSuggestions.Suggestion(meal_name="Upma", reason="Quick and light"),
            ClaudeSwapSuggestions.Suggestion(meal_name="Dosa", reason="South Indian variety"),
            ClaudeSwapSuggestions.Suggestion(meal_name="Poha", reason="Easy to make"),
        ]
    )
    assert len(ss.suggestions) == 3


def test_claude_grocery_extract():
    ge = ClaudeGroceryExtract(
        items=[
            ClaudeGroceryExtract.Item(name="paneer", quantity=500, unit="g", category="dairy"),
            ClaudeGroceryExtract.Item(name="tomato", quantity=1, unit="kg", category="vegetable"),
        ]
    )
    assert len(ge.items) == 2
    assert ge.items[0].name == "paneer"
