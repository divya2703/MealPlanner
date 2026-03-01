"""Claude API integration for meal planning intelligence."""

import json
import logging
from datetime import date, timedelta

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DailyPlan, MealHistory, PlannedMeal, UserPreferences, WeeklyPlan
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
from app.schemas import ClaudeGroceryExtract, ClaudeMealPlan, ClaudeSwapSuggestions

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _get_recent_meals(db: Session, days: int = 14) -> list[str]:
    """Get recently cooked meal names to avoid repeats."""
    cutoff = date.today() - timedelta(days=days)
    history = db.query(MealHistory.meal_name).filter(MealHistory.cooked_date >= cutoff).all()
    return list({h.meal_name for h in history})


def _get_user_prefs(db: Session) -> UserPreferences:
    """Get user preferences, creating defaults if needed."""
    prefs = db.query(UserPreferences).first()
    if not prefs:
        prefs = UserPreferences(
            whatsapp_number=settings.user_whatsapp_number,
            family_size=settings.family_size,
        )
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def _extract_tool_input(response: anthropic.types.Message, tool_name: str) -> dict | None:
    """Extract tool input from Claude's response."""
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    return None


def generate_weekly_plan(db: Session) -> WeeklyPlan | None:
    """Generate a 7-day meal plan using Claude."""
    prefs = _get_user_prefs(db)
    recent_meals = _get_recent_meals(db)

    system_prompt = WEEKLY_PLAN_SYSTEM_PROMPT.format(
        family_size=prefs.family_size,
        month_name=get_month_name(),
        seasonal_veggies=get_seasonal_veggies(),
        max_prep_time=prefs.max_prep_time_minutes,
        spice_level=prefs.spice_level,
        dislikes=", ".join(prefs.dislikes) or "none",
        favorites=", ".join(prefs.favorites) or "none specified",
        recent_meals=", ".join(recent_meals) or "none",
    )

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=4096,
        system=system_prompt,
        tools=[SUBMIT_WEEKLY_PLAN_TOOL],
        tool_choice={"type": "tool", "name": "submit_weekly_plan"},
        messages=[{"role": "user", "content": "Generate a meal plan for this week starting Monday."}],
    )

    plan_data = _extract_tool_input(response, "submit_weekly_plan")
    if not plan_data:
        logger.error("Claude did not return a weekly plan via tool use")
        return None

    parsed = ClaudeMealPlan(**plan_data)

    # Calculate week start (next Monday)
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    week_start = today + timedelta(days=days_until_monday)
    # If today is Sunday and we're generating, start tomorrow (Monday)
    if today.weekday() == 6:
        week_start = today + timedelta(days=1)

    weekly_plan = WeeklyPlan(week_start=week_start, status="draft")
    db.add(weekly_plan)
    db.flush()

    for i, day_plan in enumerate(sorted(parsed.days, key=lambda d: DAY_ORDER.index(d.day.lower()))):
        plan_date = week_start + timedelta(days=i)
        daily = DailyPlan(weekly_plan_id=weekly_plan.id, plan_date=plan_date)
        db.add(daily)
        db.flush()

        for meal_type, meal_name in [
            ("breakfast", day_plan.breakfast),
            ("lunch", day_plan.lunch),
            ("dinner", day_plan.dinner),
        ]:
            pm = PlannedMeal(
                daily_plan_id=daily.id,
                meal_type=meal_type,
                meal_name=meal_name,
            )
            db.add(pm)

    db.commit()
    db.refresh(weekly_plan)
    return weekly_plan


def get_swap_suggestions(
    db: Session, day: str, meal_type: str, current_meal: str, other_meals: list[str]
) -> list[dict] | None:
    """Get 3 alternative meal suggestions for swapping."""
    recent_meals = _get_recent_meals(db)

    system_prompt = SWAP_SUGGESTIONS_SYSTEM_PROMPT.format(
        meal_type=meal_type,
        day=day,
        current_meal=current_meal,
        other_meals=", ".join(other_meals) or "none",
        month_name=get_month_name(),
        seasonal_veggies=get_seasonal_veggies(),
        recent_meals=", ".join(recent_meals) or "none",
    )

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=system_prompt,
        tools=[SUBMIT_SWAP_SUGGESTIONS_TOOL],
        tool_choice={"type": "tool", "name": "submit_swap_suggestions"},
        messages=[{"role": "user", "content": f"Suggest 3 alternatives to replace {current_meal}."}],
    )

    data = _extract_tool_input(response, "submit_swap_suggestions")
    if not data:
        logger.error("Claude did not return swap suggestions")
        return None

    parsed = ClaudeSwapSuggestions(**data)
    return [{"meal_name": s.meal_name, "reason": s.reason} for s in parsed.suggestions]


def extract_grocery_list(
    db: Session, meals: list[str], pantry_items: list[str] | None = None
) -> list[dict] | None:
    """Extract aggregated ingredient list for given meals using Claude."""
    prefs = _get_user_prefs(db)

    system_prompt = INGREDIENT_EXTRACTION_SYSTEM_PROMPT.format(
        family_size=prefs.family_size,
        pantry_items=", ".join(pantry_items) if pantry_items else "none specified",
        meals_list="\n".join(f"- {m}" for m in meals),
    )

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=4096,
        system=system_prompt,
        tools=[SUBMIT_GROCERY_LIST_TOOL],
        tool_choice={"type": "tool", "name": "submit_grocery_list"},
        messages=[{"role": "user", "content": "Extract the ingredient list for these meals."}],
    )

    data = _extract_tool_input(response, "submit_grocery_list")
    if not data:
        logger.error("Claude did not return grocery list")
        return None

    parsed = ClaudeGroceryExtract(**data)
    return [item.model_dump() for item in parsed.items]


def get_freeform_response(message: str) -> str:
    """Get a freeform response from Claude for general queries."""
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        system=FREEFORM_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    return response.content[0].text


def format_weekly_plan(weekly_plan: WeeklyPlan) -> str:
    """Format a weekly plan for WhatsApp display."""
    lines = ["*Weekly Meal Plan* 🍽️\n"]

    for daily in sorted(weekly_plan.daily_plans, key=lambda d: d.plan_date):
        day_name = daily.plan_date.strftime("%A")
        date_str = daily.plan_date.strftime("%d %b")
        lines.append(f"*{day_name} ({date_str})*")
        for pm in sorted(daily.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type)):
            emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙"}.get(pm.meal_type, "🍽️")
            lines.append(f"  {emoji} {pm.meal_type.title()}: {pm.meal_name}")
        lines.append("")

    lines.append("Reply *1* to approve, *2* to regenerate, or *swap [day] [meal]* to change a specific meal.")
    return "\n".join(lines)


def format_daily_meals(daily_plan: DailyPlan) -> str:
    """Format a single day's meals for WhatsApp display."""
    day_name = daily_plan.plan_date.strftime("%A, %d %b")
    lines = [f"*{day_name}*\n"]
    for pm in sorted(daily_plan.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type)):
        emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙"}.get(pm.meal_type, "🍽️")
        lines.append(f"{emoji} *{pm.meal_type.title()}:* {pm.meal_name}")
    return "\n".join(lines)
