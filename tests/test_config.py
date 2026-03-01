"""Tests for app.config."""

import os

from app.config import Settings


def test_default_settings():
    s = Settings(
        _env_file=None,
        anthropic_api_key="",
        twilio_account_sid="",
        twilio_auth_token="",
    )
    assert s.claude_model == "claude-sonnet-4-20250514"
    assert s.database_url == "sqlite:///./meal_plans.db"
    assert s.family_size == 3
    assert s.log_level == "INFO"
    assert s.twilio_whatsapp_from == "whatsapp:+14155238886"


def test_settings_override():
    s = Settings(
        _env_file=None,
        anthropic_api_key="sk-test",
        twilio_account_sid="AC123",
        twilio_auth_token="tok",
        family_size=5,
        log_level="DEBUG",
    )
    assert s.anthropic_api_key == "sk-test"
    assert s.family_size == 5
    assert s.log_level == "DEBUG"
