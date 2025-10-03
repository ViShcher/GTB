import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    bot_token: str = os.getenv("BOT_TOKEN", "")
    webhook_secret_path: str = os.getenv("WEBHOOK_SECRET_PATH", "webhook/secret")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./db.sqlite3")

    @property
    def public_base_url(self) -> str:
        # Railway прокидывает домен; можно переопределить через BASE_URL_OVERRIDE
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
        path = self.webhook_secret_path.strip("/")
        return f"{base}/{path}"

settings = Settings()
