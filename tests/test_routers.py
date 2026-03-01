"""Tests for FastAPI routers — health check and WhatsApp webhook."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def client():
    """Test client with in-memory DB."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("app.routers.whatsapp.handle_message")
def test_whatsapp_webhook_valid(mock_handle, client):
    response = client.post(
        "/webhook/whatsapp",
        data={"Body": "help", "From": "whatsapp:+911234567890"},
    )
    assert response.status_code == 200
    assert "Response" in response.text
    mock_handle.assert_called_once()
    args = mock_handle.call_args[0]
    assert args[1] == "whatsapp:+911234567890"
    assert args[2] == "help"


@patch("app.routers.whatsapp.handle_message")
def test_whatsapp_webhook_empty_body(mock_handle, client):
    response = client.post(
        "/webhook/whatsapp",
        data={"Body": "", "From": "whatsapp:+911234567890"},
    )
    assert response.status_code == 200
    mock_handle.assert_not_called()


@patch("app.routers.whatsapp.handle_message", side_effect=Exception("boom"))
def test_whatsapp_webhook_handles_errors(mock_handle, client):
    response = client.post(
        "/webhook/whatsapp",
        data={"Body": "plan", "From": "whatsapp:+911234567890"},
    )
    # Should still return 200 (Twilio expects it)
    assert response.status_code == 200


@patch("app.routers.telegram.handle_message")
def test_telegram_webhook(mock_handle, client):
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 12345, "type": "private"},
            "from": {"id": 12345},
            "text": "help",
        },
    }
    response = client.post("/webhook/telegram", json=update)
    assert response.status_code == 200
    mock_handle.assert_called_once()
    args = mock_handle.call_args[0]
    assert args[1] == "tg:12345"
    assert args[2] == "help"
