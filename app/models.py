import json
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# --- Household Group ---


class HouseholdGroup(Base):
    __tablename__ = "household_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- User Preferences ---


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column("whatsapp_number", String, unique=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("household_groups.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    family_size: Mapped[int] = mapped_column(Integer, default=3)
    spice_level: Mapped[str] = mapped_column(String, default="medium")  # mild/medium/spicy
    cuisine_preference: Mapped[str] = mapped_column(String, default="indian_vegetarian")
    max_prep_time_minutes: Mapped[int] = mapped_column(Integer, default=60)
    dislikes_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    favorites_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    away_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    away_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def dislikes(self) -> list[str]:
        return json.loads(self.dislikes_json)

    @property
    def favorites(self) -> list[str]:
        return json.loads(self.favorites_json)

    def is_home(self, check_date: date | None = None) -> bool:
        if check_date is None:
            check_date = date.today()
        if self.away_from and self.away_until:
            return not (self.away_from <= check_date <= self.away_until)
        return True

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        uid = self.user_id
        if uid.startswith("whatsapp:"):
            return uid.replace("whatsapp:", "")
        if uid.startswith("tg:"):
            return f"TG-{uid.removeprefix('tg:')}"
        return uid


# --- Meal & Ingredient Catalog ---


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    cuisine: Mapped[str] = mapped_column(String, default="indian")
    meal_types_json: Mapped[str] = mapped_column(Text, default='["lunch", "dinner"]')  # JSON list
    prep_time_minutes: Mapped[int] = mapped_column(Integer, default=30)
    complexity: Mapped[str] = mapped_column(String, default="medium")  # easy/medium/hard
    seasonal_months_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of month numbers
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    ingredients: Mapped[list["MealIngredient"]] = relationship(back_populates="meal", cascade="all, delete-orphan")

    @property
    def meal_types(self) -> list[str]:
        return json.loads(self.meal_types_json)

    @property
    def seasonal_months(self) -> list[int]:
        return json.loads(self.seasonal_months_json)


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    category: Mapped[str] = mapped_column(String)  # vegetable/grain/spice/dairy/pulse/oil/other
    unit: Mapped[str] = mapped_column(String, default="g")  # g/kg/ml/l/pieces/bunch
    is_staple: Mapped[bool] = mapped_column(Boolean, default=False)
    swiggy_search_term: Mapped[str | None] = mapped_column(String, nullable=True)

    meal_ingredients: Mapped[list["MealIngredient"]] = relationship(back_populates="ingredient")


class MealIngredient(Base):
    __tablename__ = "meal_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity_per_serving: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="g")

    meal: Mapped["Meal"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="meal_ingredients")


# --- Weekly Plan Hierarchy ---


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("household_groups.id"), nullable=True, index=True)
    week_start: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft/approved/active/completed
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    daily_plans: Mapped[list["DailyPlan"]] = relationship(back_populates="weekly_plan", cascade="all, delete-orphan")


class DailyPlan(Base):
    __tablename__ = "daily_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekly_plan_id: Mapped[int] = mapped_column(ForeignKey("weekly_plans.id"))
    plan_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="planned")  # planned/confirmed/completed

    weekly_plan: Mapped["WeeklyPlan"] = relationship(back_populates="daily_plans")
    planned_meals: Mapped[list["PlannedMeal"]] = relationship(back_populates="daily_plan", cascade="all, delete-orphan")


class PlannedMeal(Base):
    __tablename__ = "planned_meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_plan_id: Mapped[int] = mapped_column(ForeignKey("daily_plans.id"))
    meal_type: Mapped[str] = mapped_column(String)  # breakfast/lunch/dinner
    meal_name: Mapped[str] = mapped_column(String)
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meals.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="planned")  # planned/confirmed/swapped/cooked/skipped

    daily_plan: Mapped["DailyPlan"] = relationship(back_populates="planned_meals")


# --- Meal Skips ---


class MealSkip(Base):
    __tablename__ = "meal_skips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column("whatsapp_number", String)
    skip_date: Mapped[date] = mapped_column(Date)
    meal_types_json: Mapped[str] = mapped_column(Text, default='["breakfast", "lunch", "dinner"]')

    @property
    def meal_types(self) -> list[str]:
        return json.loads(self.meal_types_json)


# --- History & Ratings ---


class MealHistory(Base):
    __tablename__ = "meal_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("household_groups.id"), nullable=True, index=True)
    meal_name: Mapped[str] = mapped_column(String)
    meal_type: Mapped[str] = mapped_column(String)
    cooked_date: Mapped[date] = mapped_column(Date)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- Pantry ---


class PantryItem(Base):
    __tablename__ = "pantry_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("household_groups.id"), nullable=True, index=True)
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredients.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String, default="g")
    low_threshold: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# --- Grocery List ---


class GroceryList(Base):
    __tablename__ = "grocery_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("household_groups.id"), nullable=True, index=True)
    weekly_plan_id: Mapped[int | None] = mapped_column(ForeignKey("weekly_plans.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/ordered/completed
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["GroceryListItem"]] = relationship(back_populates="grocery_list", cascade="all, delete-orphan")


class GroceryListItem(Base):
    __tablename__ = "grocery_list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grocery_list_id: Mapped[int] = mapped_column(ForeignKey("grocery_lists.id"))
    ingredient_name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, default="other")
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="g")
    is_bought: Mapped[bool] = mapped_column(Boolean, default=False)
    swiggy_search_term: Mapped[str | None] = mapped_column(String, nullable=True)

    grocery_list: Mapped["GroceryList"] = relationship(back_populates="items")


# --- Conversation State ---


class ConversationState(Base):
    __tablename__ = "conversation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column("whatsapp_number", String)
    flow_name: Mapped[str] = mapped_column(String)  # weekly_plan/swap/rating/grocery/etc.
    step: Mapped[str] = mapped_column(String)  # current step in the flow
    context_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON context data
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    @property
    def context(self) -> dict:
        return json.loads(self.context_json)

    @context.setter
    def context(self, value: dict):
        self.context_json = json.dumps(value)
