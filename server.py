from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BotCommand, MenuButtonDefault
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import settings
from db import init_db
from seed_data import ensure_seed_data
from routers import basic_router, profile_router, training_router, cardio_router, reports_router

# ================================================================
# Инициализация FastAPI и бота
# ================================================================
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

# Сначала создаём бота и диспетчер
bot = Bot(
    settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# И только потом подключаем роутеры
# (порядок важен, чтобы кардио не перехватывалось силовыми)
dp.include_router(profile_router)
dp.include_router(cardio_router)
dp.include_router(training_router)
dp.include_router(basic_router)
dp.include_router(reports_router)
dp.include_router(feedback_router)

# ================================================================
# События запуска и остановки
# ================================================================
@app.on_event("startup")
async def on_startup():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")

    # Инициализация базы и сид
    await init_db(settings.database_url)
    await ensure_seed_data()

    # Команды бота
    await bot.delete_my_commands()
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    # Устанавливаем вебхук
    await bot.set_webhook(settings.webhook_url, drop_pending_updates=True)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

# ================================================================
# Вебхук
# ================================================================
@app.post(f"/{settings.webhook_path.strip('/')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}
