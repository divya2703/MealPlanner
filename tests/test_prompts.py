"""Tests for app.prompts.meal_planning — prompt templates and tool definitions."""

from app.prompts.meal_planning import (
    FREEFORM_SYSTEM_PROMPT,
    INGREDIENT_EXTRACTION_SYSTEM_PROMPT,
    SUBMIT_GROCERY_LIST_TOOL,
    SUBMIT_SWAP_SUGGESTIONS_TOOL,
    SUBMIT_WEEKLY_PLAN_TOOL,
    SWAP_SUGGESTIONS_SYSTEM_PROMPT,
    WEEKLY_PLAN_SYSTEM_PROMPT,
    get_month_name,
    get_seasonal_veggies,
)


def test_weekly_plan_prompt_has_placeholders():
    assert "{family_size}" in WEEKLY_PLAN_SYSTEM_PROMPT
    assert "{month_name}" in WEEKLY_PLAN_SYSTEM_PROMPT
    assert "{seasonal_veggies}" in WEEKLY_PLAN_SYSTEM_PROMPT
    assert "{spice_level}" in WEEKLY_PLAN_SYSTEM_PROMPT
    assert "{dislikes}" in WEEKLY_PLAN_SYSTEM_PROMPT
    assert "{recent_meals}" in WEEKLY_PLAN_SYSTEM_PROMPT


def test_weekly_plan_prompt_formats():
    result = WEEKLY_PLAN_SYSTEM_PROMPT.format(
        family_size=3,
        month_name="March",
        seasonal_veggies="spinach, carrots",
        max_prep_time=60,
        spice_level="medium",
        dislikes="none",
        favorites="none",
        recent_meals="none",
    )
    assert "family of 3" in result
    assert "March" in result
    assert "spinach" in result


def test_swap_prompt_has_placeholders():
    assert "{meal_type}" in SWAP_SUGGESTIONS_SYSTEM_PROMPT
    assert "{day}" in SWAP_SUGGESTIONS_SYSTEM_PROMPT
    assert "{current_meal}" in SWAP_SUGGESTIONS_SYSTEM_PROMPT


def test_ingredient_extraction_prompt_has_placeholders():
    assert "{family_size}" in INGREDIENT_EXTRACTION_SYSTEM_PROMPT
    assert "{pantry_items}" in INGREDIENT_EXTRACTION_SYSTEM_PROMPT
    assert "{meals_list}" in INGREDIENT_EXTRACTION_SYSTEM_PROMPT


def test_get_seasonal_veggies():
    result = get_seasonal_veggies(1)
    assert "cauliflower" in result
    assert "green peas" in result


def test_get_seasonal_veggies_returns_string():
    result = get_seasonal_veggies(7)
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_month_name():
    assert get_month_name(1) == "January"
    assert get_month_name(3) == "March"
    assert get_month_name(12) == "December"


def test_submit_weekly_plan_tool_schema():
    assert SUBMIT_WEEKLY_PLAN_TOOL["name"] == "submit_weekly_plan"
    schema = SUBMIT_WEEKLY_PLAN_TOOL["input_schema"]
    assert "days" in schema["properties"]
    items = schema["properties"]["days"]["items"]
    assert "day" in items["properties"]
    assert "breakfast" in items["properties"]
    assert "lunch" in items["properties"]
    assert "dinner" in items["properties"]


def test_submit_swap_tool_schema():
    assert SUBMIT_SWAP_SUGGESTIONS_TOOL["name"] == "submit_swap_suggestions"
    schema = SUBMIT_SWAP_SUGGESTIONS_TOOL["input_schema"]
    assert "suggestions" in schema["properties"]


def test_submit_grocery_tool_schema():
    assert SUBMIT_GROCERY_LIST_TOOL["name"] == "submit_grocery_list"
    schema = SUBMIT_GROCERY_LIST_TOOL["input_schema"]
    assert "items" in schema["properties"]
    item_props = schema["properties"]["items"]["items"]["properties"]
    assert "name" in item_props
    assert "quantity" in item_props
    assert "unit" in item_props
    assert "category" in item_props


def test_freeform_prompt_not_empty():
    assert len(FREEFORM_SYSTEM_PROMPT) > 0
    assert "Indian vegetarian" in FREEFORM_SYSTEM_PROMPT
