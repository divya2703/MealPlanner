"""Grocery list management — aggregation, pantry tracking, Swiggy list formatting."""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    DailyPlan,
    GroceryList,
    GroceryListItem,
    PantryItem,
    PlannedMeal,
    WeeklyPlan,
)
from app.services.meal_planner import extract_grocery_list

logger = logging.getLogger(__name__)

# Swiggy Instamart search URL template
SWIGGY_SEARCH_URL = "https://www.swiggy.com/instamart/search?query={query}"


def generate_grocery_list(db: Session, weekly_plan: WeeklyPlan, group_id: int | None = None) -> GroceryList | None:
    """Generate a grocery list for an approved weekly plan using Claude."""
    # Collect all meal names from the plan
    meals = []
    for daily in weekly_plan.daily_plans:
        for pm in daily.planned_meals:
            meals.append(pm.meal_name)

    # Get current pantry items to exclude, filtered by group_id
    pantry_query = db.query(PantryItem).filter(PantryItem.quantity > 0)
    if group_id is not None:
        pantry_query = pantry_query.filter(PantryItem.group_id == group_id)
    pantry = pantry_query.all()
    pantry_items = [f"{p.name} ({p.quantity} {p.unit})" for p in pantry]

    items = extract_grocery_list(db, meals, pantry_items)
    if not items:
        return None

    grocery_list = GroceryList(weekly_plan_id=weekly_plan.id, status="pending")
    grocery_list.group_id = group_id
    db.add(grocery_list)
    db.flush()

    for item in items:
        gli = GroceryListItem(
            grocery_list_id=grocery_list.id,
            ingredient_name=item["name"],
            category=item.get("category", "other"),
            quantity=item["quantity"],
            unit=item["unit"],
            swiggy_search_term=item["name"],  # Default to ingredient name
        )
        db.add(gli)

    db.commit()
    db.refresh(grocery_list)
    return grocery_list


def format_grocery_list(grocery_list: GroceryList) -> str:
    """Format grocery list for WhatsApp display, grouped by category."""
    # Group items by category
    by_category: dict[str, list[GroceryListItem]] = {}
    for item in grocery_list.items:
        by_category.setdefault(item.category, []).append(item)

    category_order = ["vegetable", "dairy", "grain", "pulse", "spice", "oil", "other"]
    category_emoji = {
        "vegetable": "🥬",
        "dairy": "🧈",
        "grain": "🌾",
        "pulse": "🫘",
        "spice": "🌶️",
        "oil": "🫒",
        "other": "📦",
    }

    lines = ["*Grocery List* 🛒\n"]

    for cat in category_order:
        items = by_category.get(cat, [])
        if not items:
            continue
        emoji = category_emoji.get(cat, "📦")
        lines.append(f"{emoji} *{cat.title()}*")
        for item in sorted(items, key=lambda i: i.ingredient_name):
            check = "✅" if item.is_bought else "⬜"
            qty = f"{item.quantity:g}" if item.quantity == int(item.quantity) else f"{item.quantity:.1f}"
            lines.append(f"  {check} {item.ingredient_name} — {qty} {item.unit}")
        lines.append("")

    lines.append("Reply *bought [items]* to mark items as purchased.")
    return "\n".join(lines)


def format_swiggy_list(grocery_list: GroceryList) -> str:
    """Format grocery list as Swiggy Instamart search links."""
    lines = ["*Swiggy Instamart Search Links* 🛍️\n"]

    unbought = [item for item in grocery_list.items if not item.is_bought]
    for item in sorted(unbought, key=lambda i: (i.category, i.ingredient_name)):
        search_term = item.swiggy_search_term or item.ingredient_name
        url = SWIGGY_SEARCH_URL.format(query=search_term.replace(" ", "+"))
        qty = f"{item.quantity:g}" if item.quantity == int(item.quantity) else f"{item.quantity:.1f}"
        lines.append(f"• {item.ingredient_name} ({qty} {item.unit})")
        lines.append(f"  {url}")

    return "\n".join(lines)


def get_daily_grocery(db: Session, target_date: date, group_id: int | None = None) -> list[dict] | None:
    """Extract grocery list for a single day's meals using Gemini."""
    if group_id is not None:
        daily = (
            db.query(DailyPlan)
            .join(WeeklyPlan)
            .filter(DailyPlan.plan_date == target_date, WeeklyPlan.group_id == group_id)
            .first()
        )
    else:
        daily = db.query(DailyPlan).filter(DailyPlan.plan_date == target_date).first()
    if not daily or not daily.planned_meals:
        return None

    meals = [pm.meal_name for pm in daily.planned_meals]

    pantry_query = db.query(PantryItem).filter(PantryItem.quantity > 0)
    if group_id is not None:
        pantry_query = pantry_query.filter(PantryItem.group_id == group_id)
    pantry = pantry_query.all()
    pantry_items = [f"{p.name} ({p.quantity} {p.unit})" for p in pantry]

    return extract_grocery_list(db, meals, pantry_items)


def format_daily_grocery(items: list[dict], label: str) -> str:
    """Format a daily grocery list for WhatsApp display."""
    by_category: dict[str, list[dict]] = {}
    for item in items:
        by_category.setdefault(item.get("category", "other"), []).append(item)

    category_order = ["vegetable", "dairy", "grain", "pulse", "spice", "oil", "other"]
    category_emoji = {
        "vegetable": "🥬", "dairy": "🧈", "grain": "🌾", "pulse": "🫘",
        "spice": "🌶️", "oil": "🫒", "other": "📦",
    }

    lines = [f"*Grocery for {label}* 🛒\n"]

    for cat in category_order:
        cat_items = by_category.get(cat, [])
        if not cat_items:
            continue
        emoji = category_emoji.get(cat, "📦")
        lines.append(f"{emoji} *{cat.title()}*")
        for item in sorted(cat_items, key=lambda i: i["name"]):
            qty = f"{item['quantity']:g}" if item["quantity"] == int(item["quantity"]) else f"{item['quantity']:.1f}"
            lines.append(f"  ⬜ {item['name']} — {qty} {item['unit']}")
        lines.append("")

    return "\n".join(lines)


def format_daily_swiggy(items: list[dict], label: str) -> str:
    """Format daily grocery as Swiggy Instamart search links."""
    lines = [f"*Swiggy Instamart for {label}* 🛍️\n"]

    for item in sorted(items, key=lambda i: (i.get("category", ""), i["name"])):
        url = SWIGGY_SEARCH_URL.format(query=item["name"].replace(" ", "+"))
        qty = f"{item['quantity']:g}" if item["quantity"] == int(item["quantity"]) else f"{item['quantity']:.1f}"
        lines.append(f"• {item['name']} ({qty} {item['unit']})")
        lines.append(f"  {url}")

    return "\n".join(lines)


def mark_items_bought(db: Session, grocery_list: GroceryList, item_names: list[str]) -> list[str]:
    """Mark items as bought in the grocery list. Returns list of matched item names."""
    matched = []
    for item in grocery_list.items:
        for name in item_names:
            if name.lower() in item.ingredient_name.lower():
                item.is_bought = True
                matched.append(item.ingredient_name)
                break
    db.commit()
    return matched


def update_pantry(db: Session, item_name: str, quantity: float, unit: str, group_id: int | None = None) -> PantryItem:
    """Update or create a pantry item."""
    pantry_query = db.query(PantryItem).filter(PantryItem.name.ilike(f"%{item_name}%"))
    if group_id is not None:
        pantry_query = pantry_query.filter(PantryItem.group_id == group_id)
    pantry_item = pantry_query.first()

    if pantry_item:
        pantry_item.quantity = quantity
        pantry_item.unit = unit
    else:
        pantry_item = PantryItem(name=item_name, quantity=quantity, unit=unit, group_id=group_id)
        db.add(pantry_item)

    db.commit()
    db.refresh(pantry_item)
    return pantry_item


def mark_depleted(db: Session, item_name: str, group_id: int | None = None) -> PantryItem | None:
    """Mark a pantry item as depleted (quantity = 0)."""
    pantry_query = db.query(PantryItem).filter(PantryItem.name.ilike(f"%{item_name}%"))
    if group_id is not None:
        pantry_query = pantry_query.filter(PantryItem.group_id == group_id)
    pantry_item = pantry_query.first()

    if pantry_item:
        pantry_item.quantity = 0
        db.commit()
        db.refresh(pantry_item)
    return pantry_item


def get_low_stock_items(db: Session, group_id: int | None = None) -> list[PantryItem]:
    """Get pantry items that are below their low threshold."""
    query = db.query(PantryItem).filter(
        PantryItem.quantity <= PantryItem.low_threshold,
        PantryItem.low_threshold > 0,
    )
    if group_id is not None:
        query = query.filter(PantryItem.group_id == group_id)
    return query.all()


def get_current_grocery_list(db: Session, group_id: int | None = None) -> GroceryList | None:
    """Get the most recent pending grocery list."""
    query = db.query(GroceryList).filter(GroceryList.status == "pending")
    if group_id is not None:
        query = query.filter(GroceryList.group_id == group_id)
    return query.order_by(GroceryList.created_at.desc()).first()


def get_today_meals(db: Session, group_id: int | None = None) -> list[PlannedMeal]:
    """Get today's planned meals."""
    today = date.today()
    if group_id is not None:
        daily = (
            db.query(DailyPlan)
            .join(WeeklyPlan)
            .filter(DailyPlan.plan_date == today, WeeklyPlan.group_id == group_id)
            .first()
        )
    else:
        daily = db.query(DailyPlan).filter(DailyPlan.plan_date == today).first()
    if not daily:
        return []
    return sorted(daily.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type))


def get_tomorrow_meals(db: Session, group_id: int | None = None) -> list[PlannedMeal]:
    """Get tomorrow's planned meals."""
    from datetime import timedelta
    tomorrow = date.today() + timedelta(days=1)
    if group_id is not None:
        daily = (
            db.query(DailyPlan)
            .join(WeeklyPlan)
            .filter(DailyPlan.plan_date == tomorrow, WeeklyPlan.group_id == group_id)
            .first()
        )
    else:
        daily = db.query(DailyPlan).filter(DailyPlan.plan_date == tomorrow).first()
    if not daily:
        return []
    return sorted(daily.planned_meals, key=lambda m: ["breakfast", "lunch", "dinner"].index(m.meal_type))
