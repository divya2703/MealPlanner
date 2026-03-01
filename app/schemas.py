from datetime import date

from pydantic import BaseModel


class PlannedMealSchema(BaseModel):
    meal_type: str  # breakfast/lunch/dinner
    meal_name: str


class DailyPlanSchema(BaseModel):
    day: str  # monday/tuesday/...
    date: date
    meals: list[PlannedMealSchema]


class WeeklyPlanSchema(BaseModel):
    week_start: date
    days: list[DailyPlanSchema]


class SwapSuggestion(BaseModel):
    meal_name: str
    reason: str


class GroceryItemSchema(BaseModel):
    name: str
    quantity: float
    unit: str
    category: str
    swiggy_search_term: str | None = None


class GroceryListSchema(BaseModel):
    items: list[GroceryItemSchema]


# Claude tool output schemas

class ClaudeMealPlan(BaseModel):
    """Schema for Claude's weekly plan tool output."""

    class DayPlan(BaseModel):
        day: str
        breakfast: str
        breakfast_calories: int = 0
        lunch: str
        lunch_calories: int = 0
        dinner: str
        dinner_calories: int = 0

    days: list[DayPlan]


class ClaudeSwapSuggestions(BaseModel):
    """Schema for Claude's swap suggestions tool output."""

    class Suggestion(BaseModel):
        meal_name: str
        reason: str

    suggestions: list[Suggestion]


class ClaudeGroceryExtract(BaseModel):
    """Schema for Claude's ingredient extraction tool output."""

    class Item(BaseModel):
        name: str
        quantity: float
        unit: str
        category: str

    items: list[Item]
