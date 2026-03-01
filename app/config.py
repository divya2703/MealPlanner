from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini API
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # User
    user_whatsapp_number: str = ""

    # Database
    database_url: str = "sqlite:///./meal_plans.db"

    # App
    log_level: str = "INFO"
    family_size: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
