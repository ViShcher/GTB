# config.py
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    bot_token: str = os.getenv("BOT_TOKEN", "")
    # Сначала берём WEBHOOK_PATH (как в Railway), если нет — WEBHOOK_SECRET_PATH, иначе дефолт
    webhook_path: str = (
        os.getenv("WEBHOOK_PATH")
        or os.getenv("WEBHOOK_SECRET_PATH")
        or "webhook/secret"
    )
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./db.sqlite3")

    @property
    def public_base_url(self) -> str:
        rail = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        override = os.getenv("BASE_URL_OVERRIDE")
        if override:
            return override.rstrip("/")
        if rail:
            return f"https://{rail}".rstrip("/")
        return "http://localhost:8080"

    @property
    def webhook_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        path = self.webhook_path.strip("/")
        return f"{base}/{path}"

settings = Settings()
