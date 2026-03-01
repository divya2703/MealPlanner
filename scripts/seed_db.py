"""Populate the database with initial seed data."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import SessionLocal, create_tables
from app.data.indian_meals import MEALS
from app.data.staple_ingredients import STAPLES
from app.models import Ingredient, Meal, UserPreferences


def seed():
    create_tables()
    db = SessionLocal()

    try:
        # Seed meals
        existing_meals = {m.name for m in db.query(Meal.name).all()}
        added_meals = 0
        for meal_data in MEALS:
            if meal_data["name"] not in existing_meals:
                meal = Meal(
                    name=meal_data["name"],
                    meal_types_json=json.dumps(meal_data["meal_types"]),
                    prep_time_minutes=meal_data["prep_time"],
                    complexity=meal_data["complexity"],
                    seasonal_months_json=json.dumps(meal_data["seasonal_months"]),
                )
                db.add(meal)
                added_meals += 1
        print(f"Added {added_meals} meals")

        # Seed staple ingredients
        existing_ingredients = {i.name for i in db.query(Ingredient.name).all()}
        added_ingredients = 0
        for staple in STAPLES:
            if staple["name"] not in existing_ingredients:
                ingredient = Ingredient(
                    name=staple["name"],
                    category=staple["category"],
                    unit=staple["unit"],
                    is_staple=True,
                    swiggy_search_term=staple["name"],
                )
                db.add(ingredient)
                added_ingredients += 1
        print(f"Added {added_ingredients} staple ingredients")

        # Seed default user preferences if none exist
        if not db.query(UserPreferences).first():
            prefs = UserPreferences(
                user_id=settings.user_whatsapp_number or "whatsapp:+910000000000",
                family_size=settings.family_size,
                spice_level="medium",
                cuisine_preference="indian_vegetarian",
                max_prep_time_minutes=60,
            )
            db.add(prefs)
            print("Added default user preferences")

        db.commit()
        print("Seed complete!")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
