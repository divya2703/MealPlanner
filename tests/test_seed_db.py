"""Tests for scripts/seed_db.py — idempotent seeding."""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Ingredient, Meal, UserPreferences


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@patch("scripts.seed_db.create_tables")
@patch("scripts.seed_db.SessionLocal")
def test_seed_populates_data(mock_session_cls, mock_create):
    Session = _make_session()
    session = Session()
    mock_session_cls.return_value = session

    from scripts.seed_db import seed
    seed()

    assert session.query(Meal).count() > 0
    assert session.query(Ingredient).count() > 0
    assert session.query(UserPreferences).count() == 1
    session.close()


@patch("scripts.seed_db.create_tables")
@patch("scripts.seed_db.SessionLocal")
def test_seed_is_idempotent(mock_session_cls, mock_create):
    Session = _make_session()
    session = Session()
    mock_session_cls.return_value = session

    from scripts.seed_db import seed
    seed()
    count1 = session.query(Meal).count()

    # Re-create mock to reset return value
    mock_session_cls.return_value = session
    seed()
    count2 = session.query(Meal).count()

    assert count1 == count2
    assert session.query(UserPreferences).count() == 1
    session.close()
