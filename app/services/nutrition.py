"""Calorie lookup via CalorieNinjas API with Gemini fallback."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CALORIENINJAS_URL = "https://api.calorieninjas.com/v1/nutrition"


def get_meal_calories(meal_name: str) -> int | None:
    """Look up estimated calories for a meal using CalorieNinjas API.

    Falls back to None if the API is unavailable or returns no data.
    The caller should use Gemini estimates as fallback.
    """
    if not settings.calorieninjas_api_key:
        return None

    try:
        # Convert meal name to a nutrition query
        # e.g., "Palak Paneer with Roti" -> "palak paneer and roti"
        query = meal_name.lower().replace(" with ", " and ").replace(" + ", " and ")

        resp = httpx.get(
            CALORIENINJAS_URL,
            params={"query": query},
            headers={"X-Api-Key": settings.calorieninjas_api_key},
            timeout=5.0,
        )

        if resp.status_code != 200:
            logger.warning(f"CalorieNinjas API error {resp.status_code} for '{meal_name}'")
            return None

        data = resp.json()
        items = data.get("items", [])
        if not items:
            return None

        # Sum calories across all food items in the meal
        total = sum(item.get("calories", 0) for item in items)
        return round(total) if total > 0 else None

    except Exception:
        logger.exception(f"CalorieNinjas lookup failed for '{meal_name}'")
        return None


def enrich_plan_calories(planned_meals: list) -> None:
    """Enrich PlannedMeal objects with CalorieNinjas calorie data.

    Updates estimated_calories in-place. Only overwrites if the API
    returns a value; keeps existing Gemini estimates as fallback.
    """
    if not settings.calorieninjas_api_key:
        return

    for pm in planned_meals:
        cals = get_meal_calories(pm.meal_name)
        if cals:
            pm.estimated_calories = cals


def get_personalized_calories(base_calories: int, portion_multiplier: float) -> int:
    """Apply portion multiplier to base calories."""
    return round(base_calories * portion_multiplier)
