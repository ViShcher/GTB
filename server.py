# server.py
import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update, BotCommand

# ---------- базовая настройка ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("gtb")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook/ShlaSaSha")

# Домен: либо явно (WEBHOOK_URL), либо из RAILWAY_PUBLIC_DOMAIN, либо хардкодишь свой домен
PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or (
    f"https://{PUBLIC_DOMAIN}{WEBHOOK_PATH}" if PUBLIC_DOMAIN else None
)
if not WEBHOOK_URL:
    raise RuntimeError("Set WEBHOOK_URL or RAILWAY_PUBLIC_DOMAIN to build webhook URL")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # раз уж включили — пусть будет

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ---------- handlers ----------
@dp.message(commands={"start"})
async def cmd_start(msg: types.Message):
    await msg.answer("Привет. Я живу на вебхуке и уже слушаю тебя.")

@dp.message()
async def echo(msg: types.Message):
    await msg.answer(f"Эхо: {msg.text}")

# ---------- aiohttp app ----------
async def handle_webhook(request: web.Request) -> web.Response:
    # Проверяем секрет, если он задан
    if WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            return web.Response(status=403, text="forbidden")

    try:
        data = await request.json()
        update = Update.model_validate(data)
        # Важно: не блокируем ответ — парсим и отправляем в диспетчер
        await dp.feed_update(bot, update)
        return web.Response(text="ok")
    except Exception:
        log.exception("Webhook handler error")
        # Телеге нужно 200, иначе она будет ретраить. Логи у нас есть.
        return web.Response(text="ok")

async def health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")

async def on_startup(app: web.Application):
    # Чистим и выставляем правильный вебхук на наш домен, с секретом и без хвоста апдейтов
    log.info("Deleting old webhook (drop_pending_updates=True)")
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Setting webhook to %s", WEBHOOK_URL)
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    # Команды, чтобы на клиенте было красиво
    await bot.set_my_commands([BotCommand(command="start", description="Запуск бота")])

async def on_shutdown(app: web.Application):
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health)
    app.router.add_get("/healthz", health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", "8080"))
    web.run_app(app, host="0.0.0.0", port=port)
