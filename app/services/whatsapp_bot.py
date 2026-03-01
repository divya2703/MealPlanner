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
    UserPreferences,
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

*Meals*
• *plan* — Generate weekly plan
• *today* / *tomorrow* — View meals
• *swap mon dinner* — Change a meal
• *suggest lunch* — Get ideas

*Grocery*
• *grocery* — Full week list
• *grocery today* — Today only
• *swiggy* / *swiggy today* — Instamart links
• *bought tomatoes, paneer* — Mark purchased
• *out of rice* — Mark depleted

*Preferences*
• *fav paneer tikka* — Add favorite
• *dislike paratha* — Exclude from plans
• *fav* / *dislikes* — View lists
• *rate 4* — Rate today's meals

*Health*
• *calories* — Today's personalized calorie breakdown
• *portion small/medium/large* — Set your portion size
• *target 1800* — Set daily calorie goal

*Profile*
• *name Priya* — Set your name
• *me* — View your profile
• *skip tomorrow breakfast lunch* — Skip meals
• *away april* — Away for a period
• *back* — Mark yourself returned

*Groups*
• *group create myflat* — Create a group
• *group join myflat* — Join a group
• *group info* — View your group

_New here? Set up with:_
*name [you]* → *group join [name]* → *dislike [foods]* → *fav [foods]*
_Your dislikes auto-adjust the plan when you're home._"""


WELCOME_TEXT = """Welcome to *Meal Planning Bot*! 🍽️

Let's get you set up in 3 quick steps:

*1.* Set your name:
   *name Divya*

*2.* Join or create a group (household):
   *group join myflat* or *group create myflat*

*3.* Add your food preferences:
   *fav paneer butter masala*
   *dislike bitter gourd*

That's it! Send *plan* to generate your first weekly meal plan.
Send *help* anytime for all commands."""


def _ensure_user_registered(db: Session, number: str) -> bool:
    """Auto-register a user if they message the bot for the first time.

    Returns True if this is a brand new user (triggers welcome).
    """
    from app.models import HouseholdGroup

    existing = db.query(UserPreferences).filter_by(user_id=number).first()
    if existing:
        return False

    from app.config import settings
    default_group = db.query(HouseholdGroup).filter_by(name="default").first()
    prefs = UserPreferences(
        user_id=number,
        family_size=settings.family_size,
        group_id=default_group.id if default_group else None,
    )
    db.add(prefs)
    db.commit()
    logger.info(f"Auto-registered new user: {number}")
    return True


def _get_user_group_id(db: Session, user_id: str) -> int | None:
    """Get the group_id for a user."""
    prefs = db.query(UserPreferences).filter_by(user_id=user_id).first()
    return prefs.group_id if prefs else None


def handle_message(db: Session, from_number: str, body: str) -> None:
    """Main entry point: route an incoming message from any platform."""
    text = body.strip()

    # Auto-register user on first message
    is_new = _ensure_user_registered(db, from_number)
    if is_new:
        send_whatsapp(from_number, WELCOME_TEXT)
        return

    # Resolve group context once
    gid = _get_user_group_id(db, from_number)

    # Keyword-based intent detection — these work regardless of active flow
    lower = text.lower().strip()

    if lower in ("help", "hi", "hello", "hey"):
        send_whatsapp(from_number, HELP_TEXT)
        return

    if lower.startswith("group ") or lower == "group":
        _handle_group_command(db, from_number, lower)
        return

    if lower in ("today", "today's meals", "todays meals"):
        _handle_today(db, from_number, gid)
        return

    if lower in ("tomorrow", "tomorrow's meals", "tomorrows meals"):
        _handle_tomorrow(db, from_number, gid)
        return

    if lower in ("calories", "cals", "kcal", "calories today"):
        _handle_calories(db, from_number, gid)
        return

    if lower in ("grocery", "list", "grocery list", "shopping list"):
        _handle_grocery_list(db, from_number, gid)
        return

    if lower in ("grocery today", "list today", "grocery for today"):
        _handle_daily_grocery(db, from_number, "today", gid)
        return

    if lower in ("grocery tomorrow", "list tomorrow", "grocery for tomorrow"):
        _handle_daily_grocery(db, from_number, "tomorrow", gid)
        return

    if lower in ("swiggy", "instamart", "swiggy list"):
        _handle_swiggy_list(db, from_number, gid)
        return

    if lower in ("swiggy today", "instamart today"):
        _handle_daily_swiggy(db, from_number, "today", gid)
        return

    if lower in ("swiggy tomorrow", "instamart tomorrow"):
        _handle_daily_swiggy(db, from_number, "tomorrow", gid)
        return

    if lower == "bought" or lower.startswith("bought "):
        _handle_bought(db, from_number, lower, gid)
        return

    if lower == "out of" or lower.startswith("out of "):
        _handle_out_of(db, from_number, lower, gid)
        return

    if lower.startswith("rate "):
        _handle_rate(db, from_number, lower, gid)
        return

    if lower.startswith("suggest"):
        _handle_suggest(db, from_number, lower)
        return

    if lower == "fav" or lower.startswith("fav ") or lower == "favorites" or lower == "favourites":
        _handle_favorites(db, from_number, lower)
        return

    if lower.startswith("dislike ") or lower == "dislikes":
        _handle_dislikes(db, from_number, lower)
        return

    if lower.startswith("skip ") or lower == "skip":
        _handle_skip(db, from_number, lower)
        return

    if lower in ("me", "profile", "status"):
        _handle_profile(db, from_number)
        return

    if lower.startswith("portion ") or lower == "portion":
        _handle_portion(db, from_number, lower)
        return

    if lower.startswith("target ") or lower == "target":
        _handle_target(db, from_number, lower)
        return

    if lower.startswith("away ") or lower == "away":
        _handle_away(db, from_number, lower)
        return

    if lower in ("back", "i'm back", "im back"):
        _handle_back(db, from_number)
        return

    if lower.startswith("name "):
        _handle_set_name(db, from_number, text)
        return

    # Check for active conversation flow
    state = _get_active_state(db, from_number)
    if state:
        _handle_flow(db, from_number, text, state, gid)
        return

    # Commands that start new flows
    if lower in ("plan", "meal plan", "weekly plan", "new plan"):
        _start_weekly_plan_flow(db, from_number, gid)

    elif lower.startswith("swap "):
        _start_swap_flow(db, from_number, lower, gid)

    else:
        # Use Gemini intent detection for natural language
        try:
            intent = meal_planner.detect_intent(text)
            intent_name = intent.get("intent", "other")

            if intent_name == "approve":
                send_whatsapp(from_number, "No active plan to approve. Send *plan* to create one.")
            elif intent_name == "regenerate":
                _start_weekly_plan_flow(db, from_number, gid)
            elif intent_name == "swap":
                day = intent.get("day", "")
                meal_type = intent.get("meal_type", "dinner")
                if day:
                    _start_swap_flow(db, from_number, f"swap {day} {meal_type}", gid)
                else:
                    send_whatsapp(from_number, "Which day do you want to swap? E.g., *swap monday dinner*")
            elif intent_name == "today":
                _handle_today(db, from_number, gid)
            elif intent_name == "tomorrow":
                _handle_tomorrow(db, from_number, gid)
            elif intent_name == "grocery":
                _handle_grocery_list(db, from_number, gid)
            elif intent_name == "grocery_today":
                _handle_daily_grocery(db, from_number, "today", gid)
            elif intent_name == "grocery_tomorrow":
                _handle_daily_grocery(db, from_number, "tomorrow", gid)
            elif intent_name == "suggest":
                _handle_suggest(db, from_number, text)
            elif intent_name == "help":
                send_whatsapp(from_number, HELP_TEXT)
            else:
                response = meal_planner.get_freeform_response(text)
                send_whatsapp(from_number, response)
        except Exception:
            logger.exception("Intent detection failed, using freeform")
            response = meal_planner.get_freeform_response(text)
            send_whatsapp(from_number, response)


# --- Conversation State Management ---


def _get_active_state(db: Session, number: str) -> ConversationState | None:
    from datetime import datetime, timedelta as td

    # Clean up stale states older than 24 hours
    cutoff = datetime.now() - td(hours=24)
    db.query(ConversationState).filter(ConversationState.updated_at < cutoff).delete()
    db.commit()

    return (
        db.query(ConversationState)
        .filter(ConversationState.user_id == number)
        .order_by(ConversationState.updated_at.desc())
        .first()
    )


def _set_state(db: Session, number: str, flow: str, step: str, context: dict | None = None) -> ConversationState:
    # Clear any existing state
    db.query(ConversationState).filter(ConversationState.user_id == number).delete()
    state = ConversationState(
        user_id=number,
        flow_name=flow,
        step=step,
        context_json=json.dumps(context or {}),
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _clear_state(db: Session, number: str):
    db.query(ConversationState).filter(ConversationState.user_id == number).delete()
    db.commit()


# --- Flow Handlers ---


def _handle_flow(db: Session, number: str, text: str, state: ConversationState, gid: int | None = None):
    """Route to the appropriate flow handler based on active state."""
    lower = text.lower().strip()

    if lower in ("cancel", "stop", "quit", "exit"):
        _clear_state(db, number)
        send_whatsapp(number, "Cancelled. Send *help* for commands.")
        return

    flow = state.flow_name

    if flow == "weekly_plan":
        _weekly_plan_flow(db, number, text, state, gid)
    elif flow == "swap":
        _swap_flow(db, number, text, state)
    elif flow == "daily_confirm":
        _daily_confirm_flow(db, number, text, state, gid)
    else:
        _clear_state(db, number)
        send_whatsapp(number, "Something went wrong. Send *help* for commands.")


def _start_weekly_plan_flow(db: Session, number: str, gid: int | None = None):
    """Generate and send a weekly plan, then wait for approval."""
    send_whatsapp(number, "Generating your weekly meal plan... This may take a moment. ⏳")

    try:
        weekly_plan = meal_planner.generate_weekly_plan(db, group_id=gid)
    except Exception:
        logger.exception("Failed to generate weekly plan")
        weekly_plan = None

    if not weekly_plan:
        send_whatsapp(number, "Sorry, I couldn't generate a plan right now. Please try again in a minute.")
        return

    formatted = meal_planner.format_weekly_plan(weekly_plan)
    send_whatsapp(number, formatted)

    _set_state(db, number, "weekly_plan", "awaiting_approval", {"plan_id": weekly_plan.id, "group_id": gid})


def _weekly_plan_flow(db: Session, number: str, text: str, state: ConversationState, gid: int | None = None):
    """Handle weekly plan approval flow."""
    ctx = state.context
    step = state.step

    if step == "awaiting_approval":
        lower = text.strip().lower()

        if lower in ("1", "ok", "yes", "approve", "looks good", "perfect"):
            plan = db.get(WeeklyPlan, ctx["plan_id"])
            if plan:
                plan.status = "approved"
                db.commit()
                send_whatsapp(number, "Plan approved! ✅\nGenerating grocery list...")

                grocery_list = grocery_manager.generate_grocery_list(db, plan, group_id=gid)
                if grocery_list:
                    formatted = grocery_manager.format_grocery_list(grocery_list)
                    send_whatsapp(number, formatted)
                    send_whatsapp(number, "Reply *swiggy* to get Swiggy Instamart search links.")
                else:
                    send_whatsapp(number, "Plan approved! I couldn't generate the grocery list, but your meals are set.")

            _clear_state(db, number)

        elif lower in ("2", "regenerate", "redo", "new"):
            # Delete old plan
            old = db.get(WeeklyPlan, ctx["plan_id"])
            if old:
                db.delete(old)
                db.commit()
            _clear_state(db, number)
            _start_weekly_plan_flow(db, number, gid)

        elif lower.startswith("swap "):
            _clear_state(db, number)
            _start_swap_flow(db, number, lower, gid)

        else:
            # Try intent detection for natural language during plan approval
            try:
                intent = meal_planner.detect_intent(text)
                intent_name = intent.get("intent", "other")

                if intent_name == "approve":
                    _weekly_plan_flow(db, number, "1", state, gid)
                elif intent_name == "regenerate":
                    _weekly_plan_flow(db, number, "2", state, gid)
                elif intent_name == "swap":
                    day = intent.get("day", "")
                    meal_type = intent.get("meal_type", "dinner")
                    if day:
                        _clear_state(db, number)
                        _start_swap_flow(db, number, f"swap {day} {meal_type}", gid)
                    else:
                        send_whatsapp(number, "Which day and meal? E.g., *swap friday dinner*")
                else:
                    send_whatsapp(number, "Reply *1* to approve, *2* to regenerate, or *swap [day] [meal]* to change a specific meal.")
            except Exception:
                send_whatsapp(number, "Reply *1* to approve, *2* to regenerate, or *swap [day] [meal]* to change a specific meal.")


def _start_swap_flow(db: Session, number: str, text: str, gid: int | None = None):
    """Parse swap command and get suggestions."""
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
    q = db.query(WeeklyPlan).filter(WeeklyPlan.status.in_(["draft", "approved", "active"]))
    if gid is not None:
        q = q.filter(WeeklyPlan.group_id == gid)
    active_plan = q.order_by(WeeklyPlan.created_at.desc()).first()
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

    suggestions = meal_planner.get_swap_suggestions(db, day, meal_type, target_meal.meal_name, other_meals, group_id=gid)
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
            pm = db.get(PlannedMeal, ctx["planned_meal_id"])
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


def send_daily_confirmation(db: Session, number: str, gid: int | None = None):
    """Send tomorrow's meals and ask for confirmation (triggered by scheduler)."""
    meals = grocery_manager.get_tomorrow_meals(db, group_id=gid)
    if not meals:
        return

    tomorrow = date.today() + timedelta(days=1)
    q = db.query(DailyPlan)
    if gid is not None:
        q = q.join(WeeklyPlan).filter(WeeklyPlan.group_id == gid)
    daily = q.filter(DailyPlan.plan_date == tomorrow).first()
    if not daily:
        return

    formatted = meal_planner.format_daily_meals(daily)
    msg = f"*Tomorrow's Meals:*\n\n{formatted}\n\nReply *ok* to confirm or *swap [day] [meal]* to change."
    send_whatsapp(number, msg)

    _set_state(db, number, "daily_confirm", "awaiting_response", {"daily_plan_id": daily.id, "group_id": gid})


def _daily_confirm_flow(db: Session, number: str, text: str, state: ConversationState, gid: int | None = None):
    """Handle daily confirmation response."""
    lower = text.strip().lower()
    ctx = state.context

    if lower in ("ok", "yes", "confirm", "1", "looks good"):
        daily = db.get(DailyPlan, ctx["daily_plan_id"])
        if daily:
            daily.status = "confirmed"
            db.commit()
        send_whatsapp(number, "Confirmed! ✅")
        _clear_state(db, number)

    elif lower.startswith("swap "):
        _clear_state(db, number)
        _start_swap_flow(db, number, lower, gid)

    else:
        send_whatsapp(number, "Reply *ok* to confirm or *swap [day] [meal]* to change.")


# --- Direct Command Handlers ---


def _handle_today(db: Session, number: str, gid: int | None = None):
    today = date.today()
    meals = grocery_manager.get_today_meals(db, group_id=gid)
    if not meals:
        send_whatsapp(number, "No meals planned for today. Send *plan* to create a weekly plan.")
        return
    # Get the DailyPlan for formatting
    q = db.query(DailyPlan)
    if gid is not None:
        q = q.join(WeeklyPlan).filter(WeeklyPlan.group_id == gid)
    daily = q.filter(DailyPlan.plan_date == today).first()
    if daily:
        send_whatsapp(number, meal_planner.format_daily_meals(daily))


def _handle_tomorrow(db: Session, number: str, gid: int | None = None):
    tomorrow = date.today() + timedelta(days=1)
    meals = grocery_manager.get_tomorrow_meals(db, group_id=gid)
    if not meals:
        send_whatsapp(number, "No meals planned for tomorrow.")
        return
    q = db.query(DailyPlan)
    if gid is not None:
        q = q.join(WeeklyPlan).filter(WeeklyPlan.group_id == gid)
    daily = q.filter(DailyPlan.plan_date == tomorrow).first()
    if daily:
        send_whatsapp(number, meal_planner.format_daily_meals(daily))


def _handle_grocery_list(db: Session, number: str, gid: int | None = None):
    gl = grocery_manager.get_current_grocery_list(db, group_id=gid)
    if not gl:
        send_whatsapp(number, "No grocery list found. Approve a meal plan first to generate one.")
        return
    send_whatsapp(number, grocery_manager.format_grocery_list(gl))


def _handle_swiggy_list(db: Session, number: str, gid: int | None = None):
    gl = grocery_manager.get_current_grocery_list(db, group_id=gid)
    if not gl:
        send_whatsapp(number, "No grocery list found. Approve a meal plan first.")
        return
    send_whatsapp(number, grocery_manager.format_swiggy_list(gl))


def _handle_daily_grocery(db: Session, number: str, day: str, gid: int | None = None):
    if day == "today":
        target = date.today()
        label = "Today"
    else:
        target = date.today() + timedelta(days=1)
        label = "Tomorrow"

    send_whatsapp(number, f"Extracting grocery list for {label.lower()}...")
    items = grocery_manager.get_daily_grocery(db, target, group_id=gid)
    if not items:
        send_whatsapp(number, f"No meals planned for {label.lower()}.")
        return
    send_whatsapp(number, grocery_manager.format_daily_grocery(items, label))


def _handle_daily_swiggy(db: Session, number: str, day: str, gid: int | None = None):
    if day == "today":
        target = date.today()
        label = "Today"
    else:
        target = date.today() + timedelta(days=1)
        label = "Tomorrow"

    send_whatsapp(number, f"Generating Swiggy links for {label.lower()}...")
    items = grocery_manager.get_daily_grocery(db, target, group_id=gid)
    if not items:
        send_whatsapp(number, f"No meals planned for {label.lower()}.")
        return
    send_whatsapp(number, grocery_manager.format_daily_swiggy(items, label))


def _handle_bought(db: Session, number: str, text: str, gid: int | None = None):
    """Handle 'bought [items]' command."""
    items_text = text.replace("bought", "", 1).strip()
    if not items_text:
        send_whatsapp(number, "Usage: *bought tomatoes, onions, paneer*")
        return

    item_names = [i.strip() for i in items_text.split(",") if i.strip()]

    # Try to match against grocery list
    gl = grocery_manager.get_current_grocery_list(db, group_id=gid)
    matched = []
    if gl:
        matched = grocery_manager.mark_items_bought(db, gl, item_names)

    # Also update pantry
    for name in item_names:
        qty_match = re.match(r"(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pieces?|bunch)?\s+(.+)", name)
        if qty_match:
            quantity = float(qty_match.group(1))
            unit = qty_match.group(2) or "pieces"
            item_name = qty_match.group(3)
        else:
            quantity = 1
            unit = "pieces"
            item_name = name

        grocery_manager.update_pantry(db, item_name, quantity, unit, group_id=gid)

    if matched:
        send_whatsapp(number, f"Marked as bought: {', '.join(matched)} ✅\nPantry updated.")
    else:
        send_whatsapp(number, f"Pantry updated with: {', '.join(item_names)} ✅")


def _handle_out_of(db: Session, number: str, text: str, gid: int | None = None):
    """Handle 'out of [item]' command."""
    item_name = text.replace("out of", "", 1).strip()
    if not item_name:
        send_whatsapp(number, "Usage: *out of tomatoes*")
        return

    result = grocery_manager.mark_depleted(db, item_name, group_id=gid)
    if result:
        send_whatsapp(number, f"Marked *{result.name}* as depleted. It will be added to the next grocery list.")
    else:
        grocery_manager.update_pantry(db, item_name, 0, "pieces", group_id=gid)
        send_whatsapp(number, f"Noted — *{item_name}* is out of stock. It will be included in the next grocery list.")


def _handle_rate(db: Session, number: str, text: str, gid: int | None = None):
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
    meals = grocery_manager.get_today_meals(db, group_id=gid)
    if not meals:
        send_whatsapp(number, "No meals planned for today to rate.")
        return

    q = db.query(DailyPlan)
    if gid is not None:
        q = q.join(WeeklyPlan).filter(WeeklyPlan.group_id == gid)
    daily = q.filter(DailyPlan.plan_date == today).first()
    if not daily:
        send_whatsapp(number, "No meals planned for today to rate.")
        return

    for pm in daily.planned_meals:
        history = MealHistory(
            meal_name=pm.meal_name,
            meal_type=pm.meal_type,
            cooked_date=today,
            rating=rating,
            group_id=gid,
        )
        db.add(history)
        pm.status = "cooked"

    db.commit()
    stars = "⭐" * rating
    send_whatsapp(number, f"Rated today's meals: {stars} ({rating}/5)\nThanks for the feedback!")


def _handle_group_command(db: Session, number: str, text: str):
    """Handle group create/join/info commands."""
    from app.models import HouseholdGroup, UserPreferences

    parts = text.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "create" and len(parts) >= 3:
        group_name = parts[2].strip().lower()
        existing = db.query(HouseholdGroup).filter_by(name=group_name).first()
        if existing:
            send_whatsapp(number, f"Group '{group_name}' already exists. Use *group join {group_name}*")
            return
        group = HouseholdGroup(name=group_name)
        db.add(group)
        db.flush()
        prefs = db.query(UserPreferences).filter_by(user_id=number).first()
        if prefs:
            prefs.group_id = group.id
        db.commit()
        send_whatsapp(number, f"Group *{group_name}* created! ✅\nOthers can join with: *group join {group_name}*")

    elif sub == "join" and len(parts) >= 3:
        group_name = parts[2].strip().lower()
        group = db.query(HouseholdGroup).filter_by(name=group_name).first()
        if not group:
            send_whatsapp(number, f"Group '{group_name}' not found. Create it with *group create {group_name}*")
            return
        prefs = db.query(UserPreferences).filter_by(user_id=number).first()
        if prefs:
            prefs.group_id = group.id
            db.commit()
        send_whatsapp(number, f"Joined group *{group_name}* ✅")

    elif sub == "info":
        prefs = db.query(UserPreferences).filter_by(user_id=number).first()
        if not prefs or not prefs.group_id:
            send_whatsapp(number, "You're not in a group. Use *group create [name]* or *group join [name]*")
            return
        group = db.get(HouseholdGroup, prefs.group_id)
        members = db.query(UserPreferences).filter_by(group_id=prefs.group_id).all()
        names = [m.display_name for m in members]
        send_whatsapp(number, f"*Group:* {group.name}\n*Members:* {', '.join(names)}")

    else:
        send_whatsapp(number, "Usage:\n• *group create [name]*\n• *group join [name]*\n• *group info*")


def _handle_suggest(db: Session, number: str, text: str):
    """Handle 'suggest [meal type/mood]' command."""
    query = text.replace("suggest", "", 1).strip()
    if not query:
        query = "a quick and easy meal for today"

    prompt = f"Suggest 3 Indian vegetarian meals for: {query}. Keep it brief — just dish names with one-line descriptions."
    response = meal_planner.get_freeform_response(prompt)
    send_whatsapp(number, response)


def _handle_favorites(db: Session, number: str, text: str):
    """Handle 'fav [meal]' — add a favorite, or list all favorites."""
    from app.models import UserPreferences

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    item = text.split(maxsplit=1)[1].strip() if " " in text else ""

    if not item or text.strip().lower() in ("fav", "favorites", "favourites"):
        # List favorites
        favs = prefs.favorites
        if not favs:
            send_whatsapp(number, "No favorites yet. Add one with *fav paneer butter masala*")
        else:
            lines = ["*Your Favorites* ❤️\n"]
            for f in favs:
                lines.append(f"• {f}")
            lines.append("\nThese get prioritized in future meal plans.")
            send_whatsapp(number, "\n".join(lines))
    else:
        # Add favorite
        favs = prefs.favorites
        item_lower = item.lower()
        if item_lower.startswith("remove "):
            # Remove a favorite
            to_remove = item_lower.replace("remove ", "").strip()
            updated = [f for f in favs if f.lower() != to_remove]
            if len(updated) == len(favs):
                send_whatsapp(number, f"'{to_remove}' is not in your favorites.")
            else:
                prefs.favorites_json = json.dumps(updated)
                db.commit()
                send_whatsapp(number, f"Removed *{to_remove}* from favorites ✅")
        else:
            if item_lower not in [f.lower() for f in favs]:
                favs.append(item)
                prefs.favorites_json = json.dumps(favs)
                db.commit()
                send_whatsapp(number, f"Added *{item}* to favorites ❤️")
            else:
                send_whatsapp(number, f"*{item}* is already in your favorites.")


def _handle_dislikes(db: Session, number: str, text: str):
    """Handle 'dislike [item]' — add a dislike, or list all dislikes."""
    from app.models import UserPreferences

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    item = text.split(maxsplit=1)[1].strip() if " " in text else ""

    if not item or text.strip().lower() == "dislikes":
        # List dislikes
        dislikes = prefs.dislikes
        if not dislikes:
            send_whatsapp(number, "No dislikes set. Add one with *dislike bitter gourd*")
        else:
            lines = ["*Your Dislikes* 🚫\n"]
            for d in dislikes:
                lines.append(f"• {d}")
            lines.append("\nThese will be excluded from meal plans.")
            send_whatsapp(number, "\n".join(lines))
    else:
        item_lower = item.lower()
        if item_lower.startswith("remove "):
            to_remove = item_lower.replace("remove ", "").strip()
            dislikes = prefs.dislikes
            updated = [d for d in dislikes if d.lower() != to_remove]
            if len(updated) == len(dislikes):
                send_whatsapp(number, f"'{to_remove}' is not in your dislikes.")
            else:
                prefs.dislikes_json = json.dumps(updated)
                db.commit()
                send_whatsapp(number, f"Removed *{to_remove}* from dislikes ✅")
        else:
            dislikes = prefs.dislikes
            if item_lower not in [d.lower() for d in dislikes]:
                dislikes.append(item)
                prefs.dislikes_json = json.dumps(dislikes)
                db.commit()
                send_whatsapp(number, f"Added *{item}* to dislikes 🚫\nThis will be excluded from future plans.")
            else:
                send_whatsapp(number, f"*{item}* is already in your dislikes.")


def _handle_away(db: Session, number: str, text: str):
    """Handle 'away [dates]' — mark user as away for a period."""
    from datetime import timedelta
    from app.models import UserPreferences

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    args = text.replace("away", "", 1).strip().lower()

    if not args:
        # Show current away status
        if prefs.away_from and prefs.away_until:
            send_whatsapp(number, f"You're marked away from *{prefs.away_from.strftime('%d %b')}* to *{prefs.away_until.strftime('%d %b')}*.\nSend *back* when you return.")
        else:
            send_whatsapp(number, "You're not marked as away.\nUsage: *away 2 weeks* or *away march* or *away 5 march to 31 march*")
        return

    today = date.today()

    # Parse common patterns
    if "month" in args or "next month" in args:
        # Away for next month
        if today.month == 12:
            start = date(today.year + 1, 1, 1)
            end = date(today.year + 1, 1, 31)
        else:
            import calendar
            next_month = today.month + 1
            year = today.year
            last_day = calendar.monthrange(year, next_month)[1]
            start = date(year, next_month, 1)
            end = date(year, next_month, last_day)
    elif "week" in args:
        # "1 week", "2 weeks", etc.
        try:
            num = int(args.split()[0])
        except (ValueError, IndexError):
            num = 1
        start = today
        end = today + timedelta(weeks=num)
    elif " to " in args:
        # "5 march to 31 march"
        import dateutil.parser as dp
        try:
            parts = args.split(" to ")
            start = dp.parse(parts[0], dayfirst=True).date()
            end = dp.parse(parts[1], dayfirst=True).date()
            # If year not specified and date is in the past, assume next year
            if start < today:
                start = start.replace(year=today.year + 1)
                end = end.replace(year=today.year + 1)
        except Exception:
            send_whatsapp(number, "Couldn't parse dates. Try: *away 1 march to 31 march* or *away 2 weeks*")
            return
    else:
        # Try parsing as a month name: "away march"
        import calendar
        month_names = {name.lower(): i for i, name in enumerate(calendar.month_name) if i}
        month_abbr = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if i}
        month_map = {**month_names, **month_abbr}

        if args in month_map:
            month_num = month_map[args]
            year = today.year if month_num >= today.month else today.year + 1
            last_day = calendar.monthrange(year, month_num)[1]
            start = date(year, month_num, 1)
            end = date(year, month_num, last_day)
        else:
            send_whatsapp(number, "Usage: *away march* or *away 2 weeks* or *away 5 march to 31 march*")
            return

    prefs.away_from = start
    prefs.away_until = end
    db.commit()

    send_whatsapp(number, f"Marked you as away from *{start.strftime('%d %b')}* to *{end.strftime('%d %b')}* ✈️\nYour dislikes won't affect meal plans during this time.\nSend *back* when you return.")


def _handle_back(db: Session, number: str):
    """Handle 'back' — clear away dates."""
    from app.models import UserPreferences

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    prefs.away_from = None
    prefs.away_until = None
    db.commit()
    send_whatsapp(number, "Welcome back! 🏠 Your preferences will be included in future meal plans.")


def _handle_skip(db: Session, number: str, text: str):
    """Handle 'skip [day] [meals]' — skip specific meals on a day.

    Examples:
        skip tomorrow breakfast lunch
        skip monday dinner
        skip today
    """
    from app.models import MealSkip

    args = text.replace("skip", "", 1).strip().lower()
    if not args:
        send_whatsapp(number, "Usage:\n• *skip tomorrow breakfast lunch*\n• *skip monday dinner*\n• *skip today* (all meals)")
        return

    parts = args.split()

    # Parse the day
    day_input = parts[0]
    today = date.today()

    if day_input == "today":
        target = today
    elif day_input == "tomorrow":
        target = today + timedelta(days=1)
    elif day_input in DAY_MAP:
        target_day = DAY_MAP[day_input]
        # Find next occurrence of that day
        day_idx = DAY_ORDER.index(target_day)
        days_ahead = (day_idx - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target = today + timedelta(days=days_ahead)
    else:
        send_whatsapp(number, f"Couldn't understand '{day_input}'. Use: today, tomorrow, or a day name.")
        return

    # Parse which meals to skip
    meal_parts = parts[1:]
    if not meal_parts:
        # Skip all meals
        skipped_meals = ["breakfast", "lunch", "dinner"]
    else:
        skipped_meals = []
        for m in meal_parts:
            if m in MEAL_TYPE_MAP:
                skipped_meals.append(MEAL_TYPE_MAP[m])
            elif m in ("and", "&", ","):
                continue
            else:
                send_whatsapp(number, f"Couldn't understand meal '{m}'. Use: breakfast, lunch, dinner.")
                return

    # Upsert skip record
    existing = db.query(MealSkip).filter(
        MealSkip.user_id == number,
        MealSkip.skip_date == target,
    ).first()

    if existing:
        existing.meal_types_json = json.dumps(skipped_meals)
    else:
        skip = MealSkip(
            user_id=number,
            skip_date=target,
            meal_types_json=json.dumps(skipped_meals),
        )
        db.add(skip)

    db.commit()

    day_label = target.strftime("%A, %d %b")
    meals_label = ", ".join(skipped_meals)
    send_whatsapp(number, f"Skipping *{meals_label}* on *{day_label}* 🚫\nYour dislikes won't affect those meals.")


def _handle_portion(db: Session, number: str, text: str):
    """Handle 'portion [small/medium/large]' — set portion size."""
    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    arg = text.replace("portion", "", 1).strip().lower()
    valid = {"small": "0.75x", "medium": "1x", "large": "1.3x"}

    if not arg or arg not in valid:
        send_whatsapp(number, f"Your portion size: *{prefs.portion_size}* ({valid.get(prefs.portion_size, '1x')})\n\nSet with: *portion small* / *portion medium* / *portion large*")
        return

    prefs.portion_size = arg
    db.commit()
    send_whatsapp(number, f"Portion size set to *{arg}* ({valid[arg]} calories) ✅")


def _handle_target(db: Session, number: str, text: str):
    """Handle 'target [kcal]' — set daily calorie target."""
    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    arg = text.replace("target", "", 1).strip()

    if not arg or not arg.isdigit():
        send_whatsapp(number, f"Your daily target: *{prefs.calorie_target} kcal*\n\nSet with: *target 1800*")
        return

    target = int(arg)
    if target < 800 or target > 5000:
        send_whatsapp(number, "Target should be between 800 and 5000 kcal.")
        return

    prefs.calorie_target = target
    db.commit()
    send_whatsapp(number, f"Daily calorie target set to *{target} kcal* ✅")


def _handle_set_name(db: Session, number: str, text: str):
    """Handle 'name [your name]' — set display name."""
    from app.models import UserPreferences

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    name = text.split(maxsplit=1)[1].strip() if " " in text else ""
    if not name:
        send_whatsapp(number, f"Your name is: *{prefs.display_name}*\nChange it with: *name Priya*")
        return

    prefs.name = name
    db.commit()
    send_whatsapp(number, f"Name set to *{name}* ✅")


def _handle_calories(db: Session, number: str, gid: int | None = None):
    """Show today's personalized calorie breakdown."""
    from app.services.nutrition import get_personalized_calories

    meals = grocery_manager.get_today_meals(db, group_id=gid)
    if not meals:
        send_whatsapp(number, "No meals planned for today.")
        return

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    mult = prefs.portion_multiplier if prefs else 1.0
    target = prefs.calorie_target if prefs else 2000

    lines = ["*Today's Calories* 📊\n"]
    total = 0
    for pm in meals:
        base = pm.estimated_calories or 0
        personal = get_personalized_calories(base, mult) if base else 0
        total += personal
        emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙"}.get(pm.meal_type, "🍽️")
        cal_str = f"{personal} kcal" if personal else "—"
        lines.append(f"{emoji} {pm.meal_type.title()}: {pm.meal_name} — *{cal_str}*")

    if total:
        remaining = target - total
        lines.append(f"\n*Your total: {total} / {target} kcal*")
        if remaining > 0:
            lines.append(f"_{remaining} kcal remaining_")
        elif remaining < 0:
            lines.append(f"_Over by {abs(remaining)} kcal_")
        if mult != 1.0:
            lines.append(f"_(Adjusted for {prefs.portion_size} portions)_")
    else:
        lines.append("\n_No calorie data. Generate a new plan to get estimates._")

    send_whatsapp(number, "\n".join(lines))


def _handle_profile(db: Session, number: str):
    """Show user's profile summary."""
    from app.models import HouseholdGroup

    prefs = db.query(UserPreferences).filter_by(user_id=number).first()
    if not prefs:
        send_whatsapp(number, "Send *hi* first to register.")
        return

    lines = [f"*Your Profile* 👤\n"]
    lines.append(f"*Name:* {prefs.display_name}")

    if prefs.group_id:
        group = db.get(HouseholdGroup, prefs.group_id)
        members = db.query(UserPreferences).filter_by(group_id=prefs.group_id).all()
        names = [m.display_name for m in members if m.user_id != number]
        lines.append(f"*Group:* {group.name}")
        if names:
            lines.append(f"*Flatmates:* {', '.join(names)}")
    else:
        lines.append("*Group:* none (use *group join [name]*)")

    favs = prefs.favorites
    if favs:
        lines.append(f"*Favorites:* {', '.join(favs)}")

    dislikes = prefs.dislikes
    if dislikes:
        lines.append(f"*Dislikes:* {', '.join(dislikes)}")

    portion_label = {"small": "0.75x", "medium": "1x", "large": "1.3x"}.get(prefs.portion_size, "1x")
    lines.append(f"*Portion:* {prefs.portion_size} ({portion_label})")
    lines.append(f"*Calorie target:* {prefs.calorie_target} kcal/day")

    if prefs.away_from and prefs.away_until:
        lines.append(f"*Away:* {prefs.away_from.strftime('%d %b')} to {prefs.away_until.strftime('%d %b')}")

    lines.append(f"\n_Send *help* for all commands._")
    send_whatsapp(number, "\n".join(lines))
