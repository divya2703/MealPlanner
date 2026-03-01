"""WhatsApp conversation state machine — routes messages to appropriate flows."""

import json
import logging
import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    ConversationState,
    DailyPlan,
    MealHistory,
    PlannedMeal,
    WeeklyPlan,
)
from app.services import grocery_manager, meal_planner
from app.services.message_sender import send_whatsapp

logger = logging.getLogger(__name__)

DAY_MAP = {
    "mon": "monday", "monday": "monday",
    "tue": "tuesday", "tuesday": "tuesday",
    "wed": "wednesday", "wednesday": "wednesday",
    "thu": "thursday", "thursday": "thursday",
    "fri": "friday", "friday": "friday",
    "sat": "saturday", "saturday": "saturday",
    "sun": "sunday", "sunday": "sunday",
}

MEAL_TYPE_MAP = {
    "b": "breakfast", "breakfast": "breakfast",
    "l": "lunch", "lunch": "lunch",
    "d": "dinner", "dinner": "dinner",
}

HELP_TEXT = """*Meal Planning Bot* 🍽️

Commands:
• *plan* — Generate a new weekly meal plan
• *today* — See today's meals
• *tomorrow* — See tomorrow's meals
• *swap [day] [meal]* — Swap a meal (e.g., swap monday dinner)
• *grocery* or *list* — View grocery list
• *swiggy* — Get Swiggy Instamart search links
• *bought [items]* — Mark items as purchased (e.g., bought tomatoes, onions)
• *out of [item]* — Mark item as depleted
• *rate [1-5]* — Rate today's meals
• *suggest [meal type]* — Get meal suggestions
• *help* — Show this menu"""


def handle_message(db: Session, from_number: str, body: str) -> None:
    """Main entry point: route an incoming WhatsApp message."""
    text = body.strip()

    # Check for active conversation flow first
    state = _get_active_state(db, from_number)
    if state:
        _handle_flow(db, from_number, text, state)
        return

    # Keyword-based intent detection
    lower = text.lower().strip()

    if lower in ("help", "hi", "hello", "hey"):
        send_whatsapp(from_number, HELP_TEXT)

    elif lower in ("plan", "meal plan", "weekly plan", "new plan"):
        _start_weekly_plan_flow(db, from_number)

    elif lower in ("today", "today's meals", "todays meals"):
        _handle_today(db, from_number)

    elif lower in ("tomorrow", "tomorrow's meals", "tomorrows meals"):
        _handle_tomorrow(db, from_number)

    elif lower.startswith("swap "):
        _start_swap_flow(db, from_number, lower)

    elif lower in ("grocery", "list", "grocery list", "shopping list"):
        _handle_grocery_list(db, from_number)

    elif lower in ("swiggy", "instamart", "swiggy list"):
        _handle_swiggy_list(db, from_number)

    elif lower == "bought" or lower.startswith("bought "):
        _handle_bought(db, from_number, lower)

    elif lower == "out of" or lower.startswith("out of "):
        _handle_out_of(db, from_number, lower)

    elif lower.startswith("rate "):
        _handle_rate(db, from_number, lower)

    elif lower.startswith("suggest"):
        _handle_suggest(db, from_number, lower)

    else:
        # Freeform fallback via Claude
        response = meal_planner.get_freeform_response(text)
        send_whatsapp(from_number, response)


# --- Conversation State Management ---


def _get_active_state(db: Session, number: str) -> ConversationState | None:
    return (
        db.query(ConversationState)
        .filter(ConversationState.whatsapp_number == number)
        .order_by(ConversationState.updated_at.desc())
        .first()
    )


def _set_state(db: Session, number: str, flow: str, step: str, context: dict | None = None) -> ConversationState:
    # Clear any existing state
    db.query(ConversationState).filter(ConversationState.whatsapp_number == number).delete()
    state = ConversationState(
        whatsapp_number=number,
        flow_name=flow,
        step=step,
        context_json=json.dumps(context or {}),
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _clear_state(db: Session, number: str):
    db.query(ConversationState).filter(ConversationState.whatsapp_number == number).delete()
    db.commit()


# --- Flow Handlers ---


def _handle_flow(db: Session, number: str, text: str, state: ConversationState):
    """Route to the appropriate flow handler based on active state."""
    lower = text.lower().strip()

    # Allow canceling any flow
    if lower in ("cancel", "stop", "quit", "exit"):
        _clear_state(db, number)
        send_whatsapp(number, "Cancelled. Send *help* for commands.")
        return

    flow = state.flow_name

    if flow == "weekly_plan":
        _weekly_plan_flow(db, number, text, state)
    elif flow == "swap":
        _swap_flow(db, number, text, state)
    elif flow == "daily_confirm":
        _daily_confirm_flow(db, number, text, state)
    else:
        _clear_state(db, number)
        send_whatsapp(number, "Something went wrong. Send *help* for commands.")


def _start_weekly_plan_flow(db: Session, number: str):
    """Generate and send a weekly plan, then wait for approval."""
    send_whatsapp(number, "Generating your weekly meal plan... This may take a moment.")

    weekly_plan = meal_planner.generate_weekly_plan(db)
    if not weekly_plan:
        send_whatsapp(number, "Sorry, I couldn't generate a plan right now. Please try again.")
        return

    formatted = meal_planner.format_weekly_plan(weekly_plan)
    send_whatsapp(number, formatted)

    _set_state(db, number, "weekly_plan", "awaiting_approval", {"plan_id": weekly_plan.id})


def _weekly_plan_flow(db: Session, number: str, text: str, state: ConversationState):
    """Handle weekly plan approval flow."""
    ctx = state.context
    step = state.step

    if step == "awaiting_approval":
        lower = text.strip().lower()

        if lower in ("1", "ok", "yes", "approve", "looks good", "perfect"):
            plan = db.query(WeeklyPlan).get(ctx["plan_id"])
            if plan:
                plan.status = "approved"
                db.commit()
                send_whatsapp(number, "Plan approved! ✅\nGenerating grocery list...")

                grocery_list = grocery_manager.generate_grocery_list(db, plan)
                if grocery_list:
                    formatted = grocery_manager.format_grocery_list(grocery_list)
                    send_whatsapp(number, formatted)
                    send_whatsapp(number, "Reply *swiggy* to get Swiggy Instamart search links.")
                else:
                    send_whatsapp(number, "Plan approved! I couldn't generate the grocery list, but your meals are set.")

            _clear_state(db, number)

        elif lower in ("2", "regenerate", "redo", "new"):
            # Delete old plan
            old = db.query(WeeklyPlan).get(ctx["plan_id"])
            if old:
                db.delete(old)
                db.commit()
            _clear_state(db, number)
            _start_weekly_plan_flow(db, number)

        elif lower.startswith("swap "):
            _clear_state(db, number)
            _start_swap_flow(db, number, lower)

        else:
            send_whatsapp(number, "Reply *1* to approve, *2* to regenerate, or *swap [day] [meal]* to change a specific meal.")


def _start_swap_flow(db: Session, number: str, text: str):
    """Parse swap command and get suggestions."""
    # Parse: swap monday dinner
    parts = text.replace("swap", "").strip().split()
    if len(parts) < 2:
        send_whatsapp(number, "Usage: *swap [day] [meal type]*\nExample: swap monday dinner")
        return

    day_input = parts[0].lower()
    meal_input = parts[1].lower()

    day = DAY_MAP.get(day_input)
    meal_type = MEAL_TYPE_MAP.get(meal_input)

    if not day:
        send_whatsapp(number, f"Couldn't recognize day '{day_input}'. Use: mon/tue/wed/thu/fri/sat/sun")
        return
    if not meal_type:
        send_whatsapp(number, f"Couldn't recognize meal type '{meal_input}'. Use: breakfast/lunch/dinner")
        return

    # Find the planned meal
    active_plan = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.status.in_(["draft", "approved", "active"]))
        .order_by(WeeklyPlan.created_at.desc())
        .first()
    )
    if not active_plan:
        send_whatsapp(number, "No active meal plan found. Send *plan* to create one.")
        return

    target_daily = None
    for daily in active_plan.daily_plans:
        if daily.plan_date.strftime("%A").lower() == day:
            target_daily = daily
            break

    if not target_daily:
        send_whatsapp(number, f"No plan found for {day.title()}.")
        return

    target_meal = None
    other_meals = []
    for pm in target_daily.planned_meals:
        if pm.meal_type == meal_type:
            target_meal = pm
        else:
            other_meals.append(pm.meal_name)

    if not target_meal:
        send_whatsapp(number, f"No {meal_type} planned for {day.title()}.")
        return

    send_whatsapp(number, f"Finding alternatives for *{target_meal.meal_name}*...")

    suggestions = meal_planner.get_swap_suggestions(db, day, meal_type, target_meal.meal_name, other_meals)
    if not suggestions:
        send_whatsapp(number, "Couldn't generate alternatives. Please try again.")
        return

    lines = [f"Alternatives for *{target_meal.meal_name}* on {day.title()} {meal_type}:\n"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"*{i}.* {s['meal_name']}")
        lines.append(f"   _{s['reason']}_")
    lines.append("\nReply with *1*, *2*, or *3* to select, or *cancel* to keep current.")

    send_whatsapp(number, "\n".join(lines))

    _set_state(db, number, "swap", "awaiting_selection", {
        "planned_meal_id": target_meal.id,
        "suggestions": suggestions,
    })


def _swap_flow(db: Session, number: str, text: str, state: ConversationState):
    """Handle swap selection."""
    ctx = state.context

    if text.strip() in ("1", "2", "3"):
        idx = int(text.strip()) - 1
        suggestions = ctx["suggestions"]
        if idx < len(suggestions):
            new_meal = suggestions[idx]["meal_name"]
            pm = db.query(PlannedMeal).get(ctx["planned_meal_id"])
            if pm:
                old_name = pm.meal_name
                pm.meal_name = new_meal
                pm.status = "swapped"
                db.commit()
                send_whatsapp(number, f"Swapped *{old_name}* → *{new_meal}* ✅")
            else:
                send_whatsapp(number, "Couldn't find the meal to swap. Please try again.")
        else:
            send_whatsapp(number, "Invalid choice. Reply 1, 2, or 3.")
            return  # Don't clear state
    else:
        send_whatsapp(number, "Reply *1*, *2*, or *3* to select, or *cancel*.")
        return

    _clear_state(db, number)


# --- Daily Confirmation Flow ---


def send_daily_confirmation(db: Session, number: str):
    """Send tomorrow's meals and ask for confirmation (triggered by scheduler)."""
    meals = grocery_manager.get_tomorrow_meals(db)
    if not meals:
        return

    tomorrow = date.today() + timedelta(days=1)
    daily = db.query(DailyPlan).filter(DailyPlan.plan_date == tomorrow).first()
    if not daily:
        return

    formatted = meal_planner.format_daily_meals(daily)
    msg = f"*Tomorrow's Meals:*\n\n{formatted}\n\nReply *ok* to confirm or *swap [day] [meal]* to change."
    send_whatsapp(number, msg)

    _set_state(db, number, "daily_confirm", "awaiting_response", {"daily_plan_id": daily.id})


def _daily_confirm_flow(db: Session, number: str, text: str, state: ConversationState):
    """Handle daily confirmation response."""
    lower = text.strip().lower()
    ctx = state.context

    if lower in ("ok", "yes", "confirm", "1", "looks good"):
        daily = db.query(DailyPlan).get(ctx["daily_plan_id"])
        if daily:
            daily.status = "confirmed"
            db.commit()
        send_whatsapp(number, "Confirmed! ✅")
        _clear_state(db, number)

    elif lower.startswith("swap "):
        _clear_state(db, number)
        _start_swap_flow(db, number, lower)

    else:
        send_whatsapp(number, "Reply *ok* to confirm or *swap [day] [meal]* to change.")


# --- Direct Command Handlers ---


def _handle_today(db: Session, number: str):
    today = date.today()
    daily = db.query(DailyPlan).filter(DailyPlan.plan_date == today).first()
    if not daily:
        send_whatsapp(number, "No meals planned for today. Send *plan* to create a weekly plan.")
        return
    formatted = meal_planner.format_daily_meals(daily)
    send_whatsapp(number, formatted)


def _handle_tomorrow(db: Session, number: str):
    tomorrow = date.today() + timedelta(days=1)
    daily = db.query(DailyPlan).filter(DailyPlan.plan_date == tomorrow).first()
    if not daily:
        send_whatsapp(number, "No meals planned for tomorrow.")
        return
    formatted = meal_planner.format_daily_meals(daily)
    send_whatsapp(number, formatted)


def _handle_grocery_list(db: Session, number: str):
    gl = grocery_manager.get_current_grocery_list(db)
    if not gl:
        send_whatsapp(number, "No grocery list found. Approve a meal plan first to generate one.")
        return
    formatted = grocery_manager.format_grocery_list(gl)
    send_whatsapp(number, formatted)


def _handle_swiggy_list(db: Session, number: str):
    gl = grocery_manager.get_current_grocery_list(db)
    if not gl:
        send_whatsapp(number, "No grocery list found. Approve a meal plan first.")
        return
    formatted = grocery_manager.format_swiggy_list(gl)
    send_whatsapp(number, formatted)


def _handle_bought(db: Session, number: str, text: str):
    """Handle 'bought [items]' command."""
    items_text = text.replace("bought", "", 1).strip()
    if not items_text:
        send_whatsapp(number, "Usage: *bought tomatoes, onions, paneer*")
        return

    item_names = [i.strip() for i in items_text.split(",") if i.strip()]

    # Try to match against grocery list
    gl = grocery_manager.get_current_grocery_list(db)
    matched = []
    if gl:
        matched = grocery_manager.mark_items_bought(db, gl, item_names)

    # Also update pantry
    for name in item_names:
        # Try to parse quantity: "2 kg tomatoes" or just "tomatoes"
        qty_match = re.match(r"(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pieces?|bunch)?\s+(.+)", name)
        if qty_match:
            quantity = float(qty_match.group(1))
            unit = qty_match.group(2) or "pieces"
            item_name = qty_match.group(3)
        else:
            quantity = 1
            unit = "pieces"
            item_name = name

        grocery_manager.update_pantry(db, item_name, quantity, unit)

    if matched:
        send_whatsapp(number, f"Marked as bought: {', '.join(matched)} ✅\nPantry updated.")
    else:
        send_whatsapp(number, f"Pantry updated with: {', '.join(item_names)} ✅")


def _handle_out_of(db: Session, number: str, text: str):
    """Handle 'out of [item]' command."""
    item_name = text.replace("out of", "", 1).strip()
    if not item_name:
        send_whatsapp(number, "Usage: *out of tomatoes*")
        return

    result = grocery_manager.mark_depleted(db, item_name)
    if result:
        send_whatsapp(number, f"Marked *{result.name}* as depleted. It will be added to the next grocery list.")
    else:
        # Create new pantry item with 0 quantity
        grocery_manager.update_pantry(db, item_name, 0, "pieces")
        send_whatsapp(number, f"Noted — *{item_name}* is out of stock. It will be included in the next grocery list.")


def _handle_rate(db: Session, number: str, text: str):
    """Handle 'rate [1-5]' command — rate today's meals."""
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        send_whatsapp(number, "Usage: *rate 4* (1-5 scale)")
        return

    rating = int(parts[1])
    if rating < 1 or rating > 5:
        send_whatsapp(number, "Rating must be between 1 and 5.")
        return

    today = date.today()
    daily = db.query(DailyPlan).filter(DailyPlan.plan_date == today).first()
    if not daily:
        send_whatsapp(number, "No meals planned for today to rate.")
        return

    for pm in daily.planned_meals:
        history = MealHistory(
            meal_name=pm.meal_name,
            meal_type=pm.meal_type,
            cooked_date=today,
            rating=rating,
        )
        db.add(history)
        pm.status = "cooked"

    db.commit()
    stars = "⭐" * rating
    send_whatsapp(number, f"Rated today's meals: {stars} ({rating}/5)\nThanks for the feedback!")


def _handle_suggest(db: Session, number: str, text: str):
    """Handle 'suggest [meal type/mood]' command."""
    query = text.replace("suggest", "", 1).strip()
    if not query:
        query = "a quick and easy meal for today"

    prompt = f"Suggest 3 Indian vegetarian meals for: {query}. Keep it brief — just dish names with one-line descriptions."
    response = meal_planner.get_freeform_response(prompt)
    send_whatsapp(number, response)
