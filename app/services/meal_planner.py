"""Gemini API integration for meal planning intelligence."""

import json
import logging
import time
from datetime import date, timedelta

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DailyPlan, MealHistory, PlannedMeal, UserPreferences, WeeklyPlan
from app.prompts.meal_planning import (
    FREEFORM_SYSTEM_PROMPT,
    INGREDIENT_EXTRACTION_SYSTEM_PROMPT,
    SWAP_SUGGESTIONS_SYSTEM_PROMPT,
    WEEKLY_PLAN_SYSTEM_PROMPT,
    get_month_name,
    get_seasonal_veggies,
)
from app.schemas import ClaudeGroceryExtract, ClaudeMealPlan, ClaudeSwapSuggestions

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


def _call_gemini(model: str, contents: str, config: types.GenerateContentConfig):
    """Call Gemini with automatic retry on rate limits."""
    for attempt in range(MAX_RETRIES):
        try:
            return _get_client().models.generate_content(
                model=model, contents=contents, config=config,
            )
        except ClientError as e:
            if e.status_code == 429 and attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Gemini rate limited, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                raise

# --- Gemini function declarations ---

WEEKLY_PLAN_FUNC = types.FunctionDeclaration(
    name="submit_weekly_plan",
    description="Submit a 7-day meal plan with breakfast, lunch, and dinner for each day.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "days": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "day": types.Schema(type="STRING", description="Day of week: monday/tuesday/.../sunday"),
                        "breakfast": types.Schema(type="STRING", description="Breakfast dish name"),
                        "breakfast_calories": types.Schema(type="INTEGER", description="Estimated calories for breakfast (per person)"),
                        "lunch": types.Schema(type="STRING", description="Lunch dish name"),
                        "lunch_calories": types.Schema(type="INTEGER", description="Estimated calories for lunch (per person)"),
                        "dinner": types.Schema(type="STRING", description="Dinner dish name"),
                        "dinner_calories": types.Schema(type="INTEGER", description="Estimated calories for dinner (per person)"),
                    },
                    required=["day", "breakfast", "breakfast_calories", "lunch", "lunch_calories", "dinner", "dinner_calories"],
                ),
            ),
        },
        required=["days"],
    ),
)

SWAP_SUGGESTIONS_FUNC = types.FunctionDeclaration(
    name="submit_swap_suggestions",
    description="Submit 3 alternative meal suggestions for swapping.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "suggestions": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "meal_name": types.Schema(type="STRING"),
                        "reason": types.Schema(type="STRING", description="Brief reason why this is a good swap"),
                    },
                    required=["meal_name", "reason"],
                ),
            ),
        },
        required=["suggestions"],
    ),
)

GROCERY_LIST_FUNC = types.FunctionDeclaration(
    name="submit_grocery_list",
    description="Submit the aggregated grocery/ingredient list for the week's meals.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "items": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "name": types.Schema(type="STRING"),
                        "quantity": types.Schema(type="NUMBER"),
                        "unit": types.Schema(type="STRING", description="One of: g, kg, ml, l, pieces, bunch"),
                        "category": types.Schema(type="STRING", description="One of: vegetable, grain, pulse, spice, dairy, oil, other"),
                    },
                    required=["name", "quantity", "unit", "category"],
                ),
            ),
        },
        required=["items"],
    ),
)


def _extract_function_args(response, function_name: str) -> dict | None:
    """Extract function call arguments from Gemini response."""
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call and part.function_call.name == function_name:
                return dict(part.function_call.args)
    return None


def _get_recent_meals(db: Session, group_id: int | None = None, days: int = 14) -> list[str]:
    """Get recently cooked meal names to avoid repeats."""
    cutoff = date.today() - timedelta(days=days)
    query = db.query(MealHistory.meal_name).filter(MealHistory.cooked_date >= cutoff)
    if group_id is not None:
        query = query.filter(MealHistory.group_id == group_id)
    history = query.all()
    return list({h.meal_name for h in history})


def _get_user_prefs(db: Session, group_id: int | None = None) -> UserPreferences:
    """Get user preferences, creating defaults if needed."""
    query = db.query(UserPreferences)
    if group_id is not None:
        query = query.filter(UserPreferences.group_id == group_id)
    prefs = query.first()
    if not prefs:
        prefs = UserPreferences(
            user_id=settings.user_whatsapp_number,
            family_size=settings.family_size,
        )
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def _get_household_context(db: Session, week_start: date, group_id: int | None = None) -> str:
    """Build context about who's home and their preferences for each day of the week."""
    from app.models import MealSkip

    query = db.query(UserPreferences)
    if group_id is not None:
        query = query.filter(UserPreferences.group_id == group_id)
    all_users = query.all()
    if len(all_users) <= 1:
        return ""

    lines = ["\n## Household Members"]
    for user in all_users:
        name = user.display_name
        day_details = []
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            day_name = day_date.strftime("%A")

            if not user.is_home(day_date):
                day_details.append((day_name, "away"))
                continue

            # Check for meal-level skips
            skip = db.query(MealSkip).filter(
                MealSkip.user_id == user.user_id,
                MealSkip.skip_date == day_date,
            ).first()

            if skip:
                skipped = skip.meal_types
                present_meals = [m for m in ["breakfast", "lunch", "dinner"] if m not in skipped]
                if not present_meals:
                    day_details.append((day_name, "away"))
                else:
                    day_details.append((day_name, f"only {', '.join(present_meals)}"))
            else:
                day_details.append((day_name, "home"))

        home_all = all(s == "home" for _, s in day_details)
        away_all = all(s == "away" for _, s in day_details)

        if home_all:
            status = "home all week"
        elif away_all:
            status = "away all week"
        else:
            parts = []
            for day_name, s in day_details:
                if s != "home":
                    parts.append(f"{day_name}: {s}")
            status = "home all week except — " + "; ".join(parts) if parts else "home all week"

        dislikes = user.dislikes
        favs = user.favorites

        lines.append(f"- **{name}**: {status}")
        if dislikes:
            lines.append(f"  Dislikes: {', '.join(dislikes)}")
        if favs:
            lines.append(f"  Favorites: {', '.join(favs)}")

    lines.append("")
    lines.append("IMPORTANT: If a meal conflicts with a household member's dislike and they are present for that meal, "
                 "add a simple alternative for them in parentheses after the meal name. "
                 'For example: "Aloo Paratha (+ Khichdi for Priya)". '
                 "If the person is away or skipping that meal, no alternative is needed.")
    return "\n".join(lines)


def generate_weekly_plan(db: Session, group_id: int | None = None) -> WeeklyPlan | None:
    """Generate a 7-day meal plan using Gemini."""
    prefs = _get_user_prefs(db, group_id=group_id)
    recent_meals = _get_recent_meals(db, group_id=group_id)

    # Gather all household favorites and dislikes
    all_users_query = db.query(UserPreferences)
    if group_id is not None:
        all_users_query = all_users_query.filter(UserPreferences.group_id == group_id)
    all_users = all_users_query.all()
    all_favorites = []
    all_dislikes = []
    for u in all_users:
        all_favorites.extend(u.favorites)
        if u.is_home():
            all_dislikes.extend(u.dislikes)

    # Calculate week start for household context
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    week_start = today + timedelta(days=days_until_monday)
    if today.weekday() == 6:
        week_start = today + timedelta(days=1)

    household_context = _get_household_context(db, week_start, group_id=group_id)

    system_prompt = WEEKLY_PLAN_SYSTEM_PROMPT.format(
        family_size=prefs.family_size,
        month_name=get_month_name(),
        seasonal_veggies=get_seasonal_veggies(),
        max_prep_time=prefs.max_prep_time_minutes,
        spice_level=prefs.spice_level,
        dislikes=", ".join(set(all_dislikes)) or "none",
        favorites=", ".join(set(all_favorites)) or "none specified",
        recent_meals=", ".join(recent_meals) or "none",
    ) + household_context

    tool = types.Tool(function_declarations=[WEEKLY_PLAN_FUNC])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=["submit_weekly_plan"]),
        ),
    )

    response = _call_gemini(
        model=settings.gemini_model,
        contents="Generate a meal plan for this week starting Monday.",
        config=config,
    )

    plan_data = _extract_function_args(response, "submit_weekly_plan")
    if not plan_data:
        logger.error("Gemini did not return a weekly plan via function call")
        return None

    # Convert proto MapComposite objects to plain dicts
    days_list = []
    for day in plan_data["days"]:
        days_list.append({
            "day": str(day["day"]),
            "breakfast": str(day["breakfast"]),
            "breakfast_calories": int(day.get("breakfast_calories", 0) or 0),
            "lunch": str(day["lunch"]),
            "lunch_calories": int(day.get("lunch_calories", 0) or 0),
            "dinner": str(day["dinner"]),
            "dinner_calories": int(day.get("dinner_calories", 0) or 0),
        })

    parsed = ClaudeMealPlan(days=days_list)

    # week_start already calculated above
    weekly_plan = WeeklyPlan(week_start=week_start, status="draft")
    weekly_plan.group_id = group_id
    db.add(weekly_plan)
    db.flush()

    for i, day_plan in enumerate(sorted(parsed.days, key=lambda d: DAY_ORDER.index(d.day.lower()))):
        plan_date = week_start + timedelta(days=i)
        daily = DailyPlan(weekly_plan_id=weekly_plan.id, plan_date=plan_date)
        db.add(daily)
        db.flush()

        for meal_type, meal_name, cals in [
            ("breakfast", day_plan.breakfast, day_plan.breakfast_calories),
            ("lunch", day_plan.lunch, day_plan.lunch_calories),
            ("dinner", day_plan.dinner, day_plan.dinner_calories),
        ]:
            pm = PlannedMeal(
                daily_plan_id=daily.id,
                meal_type=meal_type,
                meal_name=meal_name,
                estimated_calories=cals or None,
            )
            db.add(pm)

    db.commit()
    db.refresh(weekly_plan)

    # Enrich with CalorieNinjas data (overwrites Gemini estimates where available)
    from app.services.nutrition import enrich_plan_calories
    all_meals = [pm for dp in weekly_plan.daily_plans for pm in dp.planned_meals]
    enrich_plan_calories(all_meals)
    db.commit()

    return weekly_plan


def get_swap_suggestions(
    db: Session, day: str, meal_type: str, current_meal: str, other_meals: list[str], group_id: int | None = None
) -> list[dict] | None:
    """Get 3 alternative meal suggestions for swapping."""
    recent_meals = _get_recent_meals(db, group_id=group_id)

    system_prompt = SWAP_SUGGESTIONS_SYSTEM_PROMPT.format(
        meal_type=meal_type,
        day=day,
        current_meal=current_meal,
        other_meals=", ".join(other_meals) or "none",
        month_name=get_month_name(),
        seasonal_veggies=get_seasonal_veggies(),
        recent_meals=", ".join(recent_meals) or "none",
    )

    tool = types.Tool(function_declarations=[SWAP_SUGGESTIONS_FUNC])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=["submit_swap_suggestions"]),
        ),
    )

    response = _call_gemini(
        model=settings.gemini_model,
        contents=f"Suggest 3 alternatives to replace {current_meal}.",
        config=config,
    )

    data = _extract_function_args(response, "submit_swap_suggestions")
    if not data:
        logger.error("Gemini did not return swap suggestions")
        return None

    suggestions = []
    for s in data["suggestions"]:
        suggestions.append({"meal_name": str(s["meal_name"]), "reason": str(s["reason"])})

    return suggestions


def extract_grocery_list(
    db: Session, meals: list[str], pantry_items: list[str] | None = None, group_id: int | None = None
) -> list[dict] | None:
    """Extract aggregated ingredient list for given meals using Gemini."""
    prefs = _get_user_prefs(db, group_id=group_id)

    system_prompt = INGREDIENT_EXTRACTION_SYSTEM_PROMPT.format(
        family_size=prefs.family_size,
        pantry_items=", ".join(pantry_items) if pantry_items else "none specified",
        meals_list="\n".join(f"- {m}" for m in meals),
    )

    tool = types.Tool(function_declarations=[GROCERY_LIST_FUNC])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=["submit_grocery_list"]),
        ),
    )

    response = _call_gemini(
        model=settings.gemini_model,
        contents="Extract the ingredient list for these meals.",
        config=config,
    )

    data = _extract_function_args(response, "submit_grocery_list")
    if not data:
        logger.error("Gemini did not return grocery list")
        return None

    items = []
    for item in data["items"]:
        items.append({
            "name": str(item["name"]),
            "quantity": float(item["quantity"]),
            "unit": str(item["unit"]),
            "category": str(item.get("category", "other")),
        })

    return items


INTENT_DETECTION_FUNC = types.FunctionDeclaration(
    name="detect_intent",
    description="Detect the user's intent from a natural language message about meal planning.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "intent": types.Schema(
                type="STRING",
                description="One of: approve, regenerate, swap, today, tomorrow, grocery, suggest, help, other",
            ),
            "day": types.Schema(
                type="STRING",
                description="Day of week if mentioned (monday/tuesday/.../sunday), or empty",
            ),
            "meal_type": types.Schema(
                type="STRING",
                description="Meal type if mentioned (breakfast/lunch/dinner), or empty",
            ),
        },
        required=["intent"],
    ),
)

INTENT_SYSTEM_PROMPT = """You are an intent classifier for a meal planning WhatsApp bot.
Classify the user's message into one of these intents:
- approve: user is happy with the plan (e.g., "looks great", "perfect", "go ahead")
- regenerate: user wants a completely new plan (e.g., "redo it", "start over", "new plan")
- swap: user wants to change a specific meal (e.g., "something else for friday dinner", "change monday breakfast")
- add_favorite: user wants to add a dish to their favorites/rotation (e.g., "add vegetable wrap in the rotation", "I want more paneer dishes", "include dosa in future plans")
- add_dislike: user wants to exclude something (e.g., "I don't like bitter gourd", "no more karela")
- today: user asks about today's meals
- tomorrow: user asks about tomorrow's meals
- grocery: user asks about the full week's grocery/shopping list
- grocery_today: user asks about grocery/ingredients needed for today
- grocery_tomorrow: user asks about grocery/ingredients needed for tomorrow
- calories: user asks about calories or nutrition
- suggest: user wants meal suggestions
- help: user needs help or instructions
- other: anything else

If the intent is swap, also extract the day and meal_type if mentioned.
If no meal_type is mentioned for a swap, default to "dinner".
If the intent is add_favorite or add_dislike, extract the food item in the "day" field.
"""


def detect_intent(message: str) -> dict:
    """Use Gemini to detect intent from natural language."""
    tool = types.Tool(function_declarations=[INTENT_DETECTION_FUNC])
    config = types.GenerateContentConfig(
        system_instruction=INTENT_SYSTEM_PROMPT,
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=["detect_intent"]),
        ),
    )

    response = _call_gemini(
        model=settings.gemini_model,
        contents=message,
        config=config,
    )

    data = _extract_function_args(response, "detect_intent")
    if not data:
        return {"intent": "other"}

    return {
        "intent": str(data.get("intent", "other")),
        "day": str(data.get("day", "")),
        "meal_type": str(data.get("meal_type", "")),
    }


def get_freeform_response(message: str) -> str:
    """Get a freeform response from Gemini for general queries."""
    config = types.GenerateContentConfig(
        system_instruction=FREEFORM_SYSTEM_PROMPT,
        max_output_tokens=500,
    )

    response = _call_gemini(
        model=settings.gemini_model,
        contents=message,
        config=config,
    )
    return response.text


def format_weekly_plan(weekly_plan: WeeklyPlan) -> str:
    """Format a weekly plan for WhatsApp display."""
    lines = ["*Weekly Meal Plan* 🍽️\n"]

    for daily in sorted(weekly_plan.daily_plans, key=lambda d: d.plan_date):
        day_name = daily.plan_date.strftime("%A")
        date_str = daily.plan_date.strftime("%d %b")
        lines.append(f"*{day_name} ({date_str})*")
        day_total = 0
        for pm in sorted(daily.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type)):
            emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙"}.get(pm.meal_type, "🍽️")
            cal_str = f" ({pm.estimated_calories} kcal)" if pm.estimated_calories else ""
            lines.append(f"  {emoji} {pm.meal_type.title()}: {pm.meal_name}{cal_str}")
            day_total += pm.estimated_calories or 0
        if day_total:
            lines.append(f"  📊 _{day_total} kcal total_")
        lines.append("")

    lines.append("Reply *1* to approve, *2* to regenerate, or *swap [day] [meal]* to change a specific meal.")
    return "\n".join(lines)


def format_daily_meals(daily_plan: DailyPlan) -> str:
    """Format a single day's meals for WhatsApp display."""
    day_name = daily_plan.plan_date.strftime("%A, %d %b")
    lines = [f"*{day_name}*\n"]
    day_total = 0
    for pm in sorted(daily_plan.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type)):
        emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙"}.get(pm.meal_type, "🍽️")
        cal_str = f" ({pm.estimated_calories} kcal)" if pm.estimated_calories else ""
        lines.append(f"{emoji} *{pm.meal_type.title()}:* {pm.meal_name}{cal_str}")
        day_total += pm.estimated_calories or 0
    if day_total:
        lines.append(f"📊 _{day_total} kcal total_")
    return "\n".join(lines)
