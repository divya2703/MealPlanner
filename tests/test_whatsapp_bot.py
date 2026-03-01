"""Tests for app.services.whatsapp_bot — command parsing, state machine, formatting.

Tests that require Claude API or Twilio are mocked.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import (
    ConversationState,
    DailyPlan,
    HouseholdGroup,
    MealHistory,
    MealSkip,
    PlannedMeal,
    UserPreferences,
    WeeklyPlan,
)
from app.services.whatsapp_bot import (
    DAY_MAP,
    HELP_TEXT,
    MEAL_TYPE_MAP,
    _clear_state,
    _get_active_state,
    _set_state,
    handle_message,
)

NUMBER = "whatsapp:+911234567890"


@pytest.fixture(autouse=True)
def _register_test_user(db):
    """Pre-register the test user so welcome flow doesn't trigger."""
    prefs = UserPreferences(user_id=NUMBER)
    db.add(prefs)
    db.commit()


# --- State Management Tests ---


def test_set_state(db):
    state = _set_state(db, NUMBER, "weekly_plan", "awaiting_approval", {"plan_id": 1})
    assert state.flow_name == "weekly_plan"
    assert state.step == "awaiting_approval"
    assert state.context == {"plan_id": 1}


def test_get_active_state_returns_none(db):
    assert _get_active_state(db, NUMBER) is None


def test_get_active_state_returns_state(db):
    _set_state(db, NUMBER, "swap", "awaiting_selection", {})
    state = _get_active_state(db, NUMBER)
    assert state is not None
    assert state.flow_name == "swap"


def test_clear_state(db):
    _set_state(db, NUMBER, "weekly_plan", "step1", {})
    _clear_state(db, NUMBER)
    assert _get_active_state(db, NUMBER) is None


def test_set_state_replaces_existing(db):
    _set_state(db, NUMBER, "weekly_plan", "step1", {})
    _set_state(db, NUMBER, "swap", "step2", {"key": "val"})

    states = db.query(ConversationState).filter_by(user_id=NUMBER).all()
    assert len(states) == 1
    assert states[0].flow_name == "swap"


# --- Constants Tests ---


def test_day_map_completeness():
    days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    mapped_days = set(DAY_MAP.values())
    assert mapped_days == days


def test_meal_type_map_completeness():
    types = {"breakfast", "lunch", "dinner"}
    mapped_types = set(MEAL_TYPE_MAP.values())
    assert mapped_types == types


def test_help_text_has_all_commands():
    commands = ["plan", "today", "tomorrow", "swap", "grocery", "bought", "out of", "rate", "suggest", "fav", "dislike", "name", "away", "back"]
    for cmd in commands:
        assert cmd in HELP_TEXT.lower(), f"Missing command: {cmd}"


# --- Command Routing Tests (with mocked external calls) ---


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_help_command(mock_send, db):
    handle_message(db, NUMBER, "help")
    mock_send.assert_called_once()
    assert "Meal Planning Bot" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_hello_shows_help(mock_send, db):
    handle_message(db, NUMBER, "hi")
    mock_send.assert_called_once()
    assert "Meal Planning Bot" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_today_no_plan(mock_send, db):
    handle_message(db, NUMBER, "today")
    mock_send.assert_called_once()
    assert "No meals planned" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_today_with_plan(mock_send, db):
    today = date.today()
    wp = WeeklyPlan(week_start=today)
    db.add(wp)
    db.flush()
    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=today)
    db.add(dp)
    db.flush()
    db.add(PlannedMeal(daily_plan_id=dp.id, meal_type="breakfast", meal_name="Poha"))
    db.commit()

    handle_message(db, NUMBER, "today")
    mock_send.assert_called_once()
    assert "Poha" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_tomorrow_no_plan(mock_send, db):
    handle_message(db, NUMBER, "tomorrow")
    mock_send.assert_called_once()
    assert "No meals planned" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
@patch("app.services.whatsapp_bot.grocery_manager.get_current_grocery_list", return_value=None)
def test_grocery_no_list(mock_gcl, mock_send, db):
    handle_message(db, NUMBER, "grocery")
    mock_send.assert_called_once()
    assert "No grocery list" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_bought_no_items(mock_send, db):
    handle_message(db, NUMBER, "bought ")
    mock_send.assert_called_once()
    assert "Usage" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
@patch("app.services.whatsapp_bot.grocery_manager.update_pantry")
@patch("app.services.whatsapp_bot.grocery_manager.get_current_grocery_list", return_value=None)
def test_bought_updates_pantry(mock_gcl, mock_pantry, mock_send, db):
    handle_message(db, NUMBER, "bought tomatoes, onions")
    # Should have called update_pantry for each item
    assert mock_pantry.call_count == 2


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_out_of_no_item(mock_send, db):
    handle_message(db, NUMBER, "out of ")
    mock_send.assert_called_once()
    assert "Usage" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_rate_invalid(mock_send, db):
    handle_message(db, NUMBER, "rate abc")
    mock_send.assert_called_once()
    assert "Usage" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_rate_out_of_range(mock_send, db):
    handle_message(db, NUMBER, "rate 6")
    mock_send.assert_called_once()
    assert "between 1 and 5" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_rate_no_plan(mock_send, db):
    handle_message(db, NUMBER, "rate 4")
    mock_send.assert_called_once()
    assert "No meals planned" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_rate_records_history(mock_send, db):
    today = date.today()
    wp = WeeklyPlan(week_start=today)
    db.add(wp)
    db.flush()
    dp = DailyPlan(weekly_plan_id=wp.id, plan_date=today)
    db.add(dp)
    db.flush()
    db.add(PlannedMeal(daily_plan_id=dp.id, meal_type="lunch", meal_name="Dal Rice"))
    db.commit()

    handle_message(db, NUMBER, "rate 4")
    history = db.query(MealHistory).all()
    assert len(history) == 1
    assert history[0].rating == 4
    assert history[0].meal_name == "Dal Rice"


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_swap_invalid_format(mock_send, db):
    handle_message(db, NUMBER, "swap monday")
    mock_send.assert_called_once()
    assert "Usage" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_swap_invalid_day(mock_send, db):
    handle_message(db, NUMBER, "swap funday dinner")
    mock_send.assert_called_once()
    assert "Couldn't recognize day" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_swap_invalid_meal_type(mock_send, db):
    handle_message(db, NUMBER, "swap monday snack")
    mock_send.assert_called_once()
    assert "Couldn't recognize meal type" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_swap_no_active_plan(mock_send, db):
    handle_message(db, NUMBER, "swap monday dinner")
    mock_send.assert_called_once()
    assert "No active meal plan" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.meal_planner.get_freeform_response", return_value="Try making Paneer Tikka!")
@patch("app.services.whatsapp_bot.send_whatsapp")
def test_freeform_fallback(mock_send, mock_claude, db):
    handle_message(db, NUMBER, "what should I cook for a party?")
    mock_claude.assert_called_once()
    mock_send.assert_called_once()
    assert "Paneer Tikka" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_cancel_clears_state(mock_send, db):
    _set_state(db, NUMBER, "weekly_plan", "awaiting_approval", {"plan_id": 1})
    handle_message(db, NUMBER, "cancel")
    assert _get_active_state(db, NUMBER) is None
    assert "Cancelled" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
@patch("app.services.whatsapp_bot.meal_planner.get_freeform_response", return_value="Suggestions here")
def test_suggest_command(mock_claude, mock_send, db):
    handle_message(db, NUMBER, "suggest breakfast")
    mock_claude.assert_called_once()
    assert "breakfast" in mock_claude.call_args[0][0]


# --- New Feature Tests ---


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_welcome_new_user(mock_send, db):
    """A completely new number should receive the welcome message."""
    new_number = "whatsapp:+919999999999"
    handle_message(db, new_number, "hi")
    mock_send.assert_called_once()
    assert "Welcome" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_group_create(mock_send, db):
    """'group create testgroup' should create the group and confirm."""
    handle_message(db, NUMBER, "group create testgroup")
    mock_send.assert_called_once()
    assert "created" in mock_send.call_args[0][1].lower()


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_group_join(mock_send, db):
    """'group join [name]' should add the user to an existing group."""
    group = HouseholdGroup(name="myflatmates")
    db.add(group)
    db.commit()

    handle_message(db, NUMBER, "group join myflatmates")
    mock_send.assert_called_once()
    assert "Joined" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_group_info(mock_send, db):
    """'group info' should display the group name when the user is in one."""
    group = HouseholdGroup(name="myapartment")
    db.add(group)
    db.flush()

    prefs = db.query(UserPreferences).filter_by(user_id=NUMBER).first()
    prefs.group_id = group.id
    db.commit()

    handle_message(db, NUMBER, "group info")
    mock_send.assert_called_once()
    assert "myapartment" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_profile_command(mock_send, db):
    """'me' should display the user's profile."""
    handle_message(db, NUMBER, "me")
    mock_send.assert_called_once()
    assert "Your Profile" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_fav_add(mock_send, db):
    """'fav paneer tikka' should add the item and confirm."""
    handle_message(db, NUMBER, "fav paneer tikka")
    mock_send.assert_called_once()
    assert "Added" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_fav_list(mock_send, db):
    """'fav' with no argument should list existing favorites."""
    import json
    prefs = db.query(UserPreferences).filter_by(user_id=NUMBER).first()
    prefs.favorites_json = json.dumps(["Palak Paneer"])
    db.commit()

    handle_message(db, NUMBER, "fav")
    mock_send.assert_called_once()
    assert "Palak Paneer" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_dislike_add(mock_send, db):
    """'dislike bitter gourd' should add the item and confirm."""
    handle_message(db, NUMBER, "dislike bitter gourd")
    mock_send.assert_called_once()
    assert "Added" in mock_send.call_args[0][1]


@patch("app.services.whatsapp_bot.send_whatsapp")
def test_skip_command(mock_send, db):
    """'skip tomorrow breakfast lunch' should record the skip and confirm."""
    handle_message(db, NUMBER, "skip tomorrow breakfast lunch")
    mock_send.assert_called_once()
    assert "Skipping" in mock_send.call_args[0][1]
