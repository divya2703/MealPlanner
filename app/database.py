import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# SQLite needs check_same_thread=False; PostgreSQL doesn't use it
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _apply_migrations():
    """Add new columns to existing tables. Safe to run repeatedly."""
    migrations = [
        "ALTER TABLE user_preferences ADD COLUMN group_id INTEGER REFERENCES household_groups(id)",
        "ALTER TABLE weekly_plans ADD COLUMN group_id INTEGER REFERENCES household_groups(id)",
        "ALTER TABLE grocery_lists ADD COLUMN group_id INTEGER REFERENCES household_groups(id)",
        "ALTER TABLE pantry_items ADD COLUMN group_id INTEGER REFERENCES household_groups(id)",
        "ALTER TABLE meal_history ADD COLUMN group_id INTEGER REFERENCES household_groups(id)",
        "ALTER TABLE planned_meals ADD COLUMN estimated_calories INTEGER",
        "ALTER TABLE user_preferences ADD COLUMN portion_size TEXT DEFAULT 'medium'",
        "ALTER TABLE user_preferences ADD COLUMN calorie_target INTEGER DEFAULT 2000",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
            except Exception:
                pass  # Column already exists
        conn.commit()


def _seed_default_group():
    """Create a default group and assign orphaned data to it."""
    from app.models import HouseholdGroup, UserPreferences, WeeklyPlan, GroceryList, PantryItem, MealHistory

    db = SessionLocal()
    try:
        group = db.query(HouseholdGroup).filter_by(name="default").first()
        if not group:
            group = HouseholdGroup(name="default")
            db.add(group)
            db.flush()

        db.query(UserPreferences).filter(UserPreferences.group_id.is_(None)).update(
            {"group_id": group.id}, synchronize_session=False
        )
        for Model in [WeeklyPlan, GroceryList, PantryItem, MealHistory]:
            db.query(Model).filter(Model.group_id.is_(None)).update(
                {"group_id": group.id}, synchronize_session=False
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("Default group seeding skipped (likely fresh DB)")
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
    _apply_migrations()
    _seed_default_group()
