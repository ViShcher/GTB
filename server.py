import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gtb")

# ── обязательные переменные окружения ───────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN. Задай переменную окружения BOT_TOKEN в Railway.")

# секрет для пути вебхука (любой случайный текст)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me_secret")

# Railway обычно пробрасывает порт в переменную PORT
PORT = int(os.getenv("PORT", "8000"))

# Пытаемся автоматически получить публичный домен Railway:
# - сначала берём PUBLIC_URL (если ты задал сам),
# - иначе RAILWAY_PUBLIC_DOMAIN (который отдаёт Railway для сервиса).
_public = os.getenv("PUBLIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if not _public:
    raise RuntimeError(
        "Не найден PUBLIC_URL или RAILWAY_PUBLIC_DOMAIN.\n"
        "Подсказка: после первого деплоя в Railway появится домен вида "
        "your-app.up.railway.app — задай PUBLIC_URL=https://your-app.up.railway.app"
    )

if not _public.startswith("http"):
    PUBLIC_URL = f"https://{_public}"
else:
    PUBLIC_URL = _public

# ── параметры вебхука ────────────────────────────────────────────────
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{PUBLIC_URL}{WEBHOOK_PATH}"

# ── инициализация бота ──────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ── хэндлеры ────────────────────────────────────────────────────────
@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я твой фитнес-бот 💪\n"
        "Команды:\n"
        "/start — приветствие\n"
        "/ping — проверка связи"
    )

@dp.message_handler(commands=["ping"])
async def cmd_ping(message: types.Message):
    await message.answer("pong 🏓")

# ── lifecycle: ставим/сносим вебхук ─────────────────────────────────
async def on_startup(dispatcher: Dispatcher):
    log.info("Deleting old webhook (drop_pending_updates=True)")
    await bot.delete_webhook(drop_pending_updates=True)

    log.info("Setting webhook to %s", WEBHOOK_URL)
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dispatcher: Dispatcher):
    log.info("Deleting webhook on shutdown")
    await bot.delete_webhook()

# ── запуск aiohttp-сервера внутри aiogram ───────────────────────────
if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=False,           # мы уже чистим апдейты при set_webhook
        host="0.0.0.0",
        port=PORT,
    )
