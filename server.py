from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BotCommand, MenuButtonDefault
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import settings
from db import init_db
from seed_data import ensure_seed_data
from routers import basic_router, profile_router, training_router, cardio_router

# ================================================================
# Инициализация FastAPI и бота
# ================================================================
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

bot = Bot(
    settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# Порядок подключения роутеров: profile -> cardio -> training -> basic
dp.include_router(profile_router)
dp.include_router(cardio_router)
dp.include_router(training_router)
dp.include_router(basic_router)

# ================================================================
# Миграция created_at (временный эндпоинт, удалить после выполнения)
# ================================================================
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

@app.get("/migrate_created_at")
async def migrate_created_at():
    """Добавляет поле created_at в workout и workoutitem, если их нет."""
    engine = create_async_engine(settings.database_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE workout ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
        ))
        await conn.execute(text(
            "ALTER TABLE workoutitem ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
        ))
    return {"status": "ok"}

# ================================================================
# События запуска и остановки
# ================================================================
@app.on_event("startup")
async def on_startup():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")

    # Инициализация базы
    await init_db(settings.database_url)
    await ensure_seed_data()

    # Команды бота
    await bot.delete_my_commands()
    await bot.set_my_commands([
        BotCommand(command="start", description="Онбординг и профиль"),
        BotCommand(command="train", description="Начать тренировку"),
        BotCommand(command="cardio", description="Кардио-тренировка"),
        BotCommand(command="help", description="Помощь и команды"),
    ])
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
