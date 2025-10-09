# config.py
import os
from typing import Optional


def _coerce_asyncpg(url: str) -> str:
    """
    Превращает sync-URL в async-URL для SQLAlchemy:
      postgres://...        -> postgresql://...
      postgresql://...      -> postgresql+asyncpg://...
    Если уже async или пусто — возвращаем как есть.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings:
    def __init__(self) -> None:
        # токен бота
        self.bot_token: str = os.getenv("BOT_TOKEN", "").strip()

        # домен, который отдаёт Railway (например gtb-production.up.railway.app)
        self.railway_public_domain: str = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()

        # путь вебхука (только путь, без домена)
        self.webhook_path: str = os.getenv("WEBHOOK_PATH", "webhook/ShlaSaSha").strip("/")

        # строка подключения к БД
        raw_db = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./db.sqlite3").strip()
        self.database_url: str = _coerce_asyncpg(raw_db)

        # ===== Новые настройки для обратной связи =====
        # токен второго бота (куда отправляем отзывы)
        fb_token = os.getenv("FEEDBACK_BOT_TOKEN", "").strip()
        self.feedback_bot_token: Optional[str] = fb_token or None

        # chat_id чата/канала/лички, куда второй бот будет слать отзывы
        fb_chat = os.getenv("FEEDBACK_CHAT_ID", "").strip()
        self.feedback_chat_id: Optional[int] = int(fb_chat) if fb_chat else None

    class Config:
        env_file = ".env"

    @property
    def webhook_url(self) -> str:
        """
        Полный URL вебхука, который мы отдаём Telegram.
        Если домен пуст (локалка) — вернёт относительный путь, что тоже ок для тестов.
        """
        base = self.railway_public_domain
        if base and not base.startswith(("http://", "https://")):
            base = "https://" + base
        if not base:
            return f"/{self.webhook_path}"
        return f"{base}/{self.webhook_path}"


# единый инстанс настроек
settings = Settings()
