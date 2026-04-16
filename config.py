from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    bot_token: str = os.getenv("BOT_TOKEN", "")
    db_url: str = os.getenv("DB_URL", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")

    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int | None = int(os.getenv("SMTP_PORT", "0") or 0) if os.getenv("SMTP_PORT") else None
    smtp_user: str | None = os.getenv("SMTP_USER")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from: str | None = os.getenv("SMTP_FROM")
    smtp_use_tls: bool = _env_bool("SMTP_USE_TLS", True)
    smtp_use_ssl: bool = _env_bool("SMTP_USE_SSL", False)

    llm_provider: str = os.getenv("LLM_PROVIDER", "stub").strip().lower()
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    app_timezone: str = os.getenv("APP_TIMEZONE", "Europe/Moscow")
    reminders_enabled: bool = _env_bool("REMINDERS_ENABLED", True)


settings = Settings()