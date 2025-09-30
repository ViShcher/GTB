# server.py — aiogram v3 (webhook, aiohttp)
import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update, BotCommand
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("gtb")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook/ShlaSaSha")
PUBLIC_URL = os.getenv("PUBLIC_URL")  # например: https://gtb-production.up.railway.app
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or (f"{PUBLIC_URL.rstrip('/')}{WEBHOOK_PATH}" if PUBLIC_URL else None)
if not WEBHOOK_URL:
    raise RuntimeError("Set WEBHOOK_URL or PUBLIC_URL to build full webhook URL")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # если задан — проверяем заголовок

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# -------- Handlers (v3 синтаксис) --------
@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    await msg.answer("Привет. Живу на вебхуке v3, всё слышу.")

@dp.message()
async def echo(msg: types.Message):
    # Простое эхо, чтобы проверить рабочий цикл
    if msg.text:
        await msg.answer(f"Эхо: {msg.text}")

# -------- AIOHTTP app / webhook --------
async def handle_webhook(request: web.Request) -> web.Response:
    if WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            return web.Response(status=403, text="forbidden")
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)  # v3: кормим диспетчер апдейтом
        return web.Response(text="ok")     # Телеге важен быстрый 200
    except Exception:
        log.exception("Webhook handler error")
        # Возвращаем 200, чтобы Телега не ретраила бесконечно
        return web.Response(text="ok")

async def health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")

async def on_startup(app: web.Application):
    log.info("Deleting old webhook (drop_pending_updates=True)")
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Setting webhook to %s", WEBHOOK_URL)
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
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
