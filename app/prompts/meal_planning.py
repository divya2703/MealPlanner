"""Claude system prompts and tool definitions for meal planning."""

from datetime import date

from app.data.seasonal_ingredients import SEASONAL_VEGETABLES

WEEKLY_PLAN_SYSTEM_PROMPT = """You are an expert Indian vegetarian meal planner for a family of {family_size}.

## Rules
- Plan breakfast, lunch, and dinner for 7 days (Monday to Sunday).
- All meals must be vegetarian (no eggs, no meat, no fish).
- Prioritize variety: do NOT repeat any dish within the same week.
- Prefer seasonal vegetables for the current month ({month_name}): {seasonal_veggies}
- Balance nutrition: include dal/lentils at least 3 times/week, paneer 2-3 times/week, rice and roti both throughout the week.
- Keep breakfasts quick (under 20 min prep where possible). Lunches and dinners can be up to {max_prep_time} minutes.
- Spice level preference: {spice_level}.
- Avoid these dishes/ingredients: {dislikes}
- Include these favorites when appropriate: {favorites}
- Recently cooked dishes to avoid repeating: {recent_meals}

## Output
Use the submit_weekly_plan tool to return your plan. Each day must have exactly 3 meals: breakfast, lunch, dinner.
Meal names should be specific (e.g., "Palak Paneer with Roti" not just "Paneer Curry").
"""

SWAP_SUGGESTIONS_SYSTEM_PROMPT = """You are an Indian vegetarian meal planner. The user wants to swap a {meal_type} meal on {day}.

Current planned meal: {current_meal}
Other meals planned for that day: {other_meals}

Suggest exactly 3 alternative meals. Each should be:
- Different from the current meal and other meals that day
- Appropriate for {meal_type}
- Indian vegetarian
- Seasonal for {month_name}: {seasonal_veggies}
- Different from recently cooked: {recent_meals}

Use the submit_swap_suggestions tool to return your suggestions.
"""

INGREDIENT_EXTRACTION_SYSTEM_PROMPT = """You are a cooking ingredient expert for Indian vegetarian cuisine.

Given a list of planned meals for a week, extract ALL ingredients needed with quantities for a family of {family_size}.

## Rules
- Be thorough: include every ingredient, even spices and garnishes.
- Aggregate quantities: if multiple meals need tomatoes, sum them up.
- Use standard Indian cooking units: kg, g, ml, l, pieces, bunch.
- Categorize each ingredient: vegetable, grain, pulse, spice, dairy, oil, other.
- For staple items (rice, oil, salt, etc.), only include if the quantity needed exceeds typical pantry amounts.
- Skip items marked as already in pantry: {pantry_items}

Meals to extract ingredients for:
{meals_list}

Use the submit_grocery_list tool to return the ingredient list.
"""

FREEFORM_SYSTEM_PROMPT = """You are a helpful Indian vegetarian meal planning assistant communicating via WhatsApp.
Keep responses concise and friendly (WhatsApp messages should be short).
You help with meal suggestions, cooking tips, and ingredient substitutions.
Always stay within Indian vegetarian cuisine unless explicitly asked otherwise.
"""

# Claude tool definitions

SUBMIT_WEEKLY_PLAN_TOOL = {
    "name": "submit_weekly_plan",
    "description": "Submit a 7-day meal plan with breakfast, lunch, and dinner for each day.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "string", "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
                        "breakfast": {"type": "string", "description": "Breakfast dish name"},
                        "lunch": {"type": "string", "description": "Lunch dish name"},
                        "dinner": {"type": "string", "description": "Dinner dish name"},
                    },
                    "required": ["day", "breakfast", "lunch", "dinner"],
                },
                "minItems": 7,
                "maxItems": 7,
            }
        },
        "required": ["days"],
    },
}

SUBMIT_SWAP_SUGGESTIONS_TOOL = {
    "name": "submit_swap_suggestions",
    "description": "Submit 3 alternative meal suggestions for swapping.",
    "input_schema": {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "meal_name": {"type": "string"},
                        "reason": {"type": "string", "description": "Brief reason why this is a good swap"},
                    },
                    "required": ["meal_name", "reason"],
                },
                "minItems": 3,
                "maxItems": 3,
            }
        },
        "required": ["suggestions"],
    },
}

SUBMIT_GROCERY_LIST_TOOL = {
    "name": "submit_grocery_list",
    "description": "Submit the aggregated grocery/ingredient list for the week's meals.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit": {"type": "string", "enum": ["g", "kg", "ml", "l", "pieces", "bunch"]},
                        "category": {"type": "string", "enum": ["vegetable", "grain", "pulse", "spice", "dairy", "oil", "other"]},
                    },
                    "required": ["name", "quantity", "unit", "category"],
                },
            }
        },
        "required": ["items"],
    },
}


def get_seasonal_veggies(month: int | None = None) -> str:
    if month is None:
        month = date.today().month
    veggies = SEASONAL_VEGETABLES.get(month, [])
    return ", ".join(veggies) if veggies else "no specific seasonal preferences"


def get_month_name(month: int | None = None) -> str:
    import calendar
    if month is None:
        month = date.today().month
    return calendar.month_name[month]
