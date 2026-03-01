"""Tests for app.config."""

from app.config import Settings


def test_default_settings():
    s = Settings(
        _env_file=None,
        gemini_api_key="",
        twilio_account_sid="",
        twilio_auth_token="",
    )
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.database_url == "sqlite:///./meal_plans.db"
    assert s.family_size == 3
    assert s.log_level == "INFO"
    assert s.twilio_whatsapp_from == "whatsapp:+14155238886"


def test_settings_override():
    s = Settings(
        _env_file=None,
        gemini_api_key="AIza-test",
        twilio_account_sid="AC123",
        twilio_auth_token="tok",
        family_size=5,
        log_level="DEBUG",
    )
    assert s.gemini_api_key == "AIza-test"
    assert s.family_size == 5
    assert s.log_level == "DEBUG"
