from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BotCommand, MenuButtonDefault

from config import settings
from db import init_db
from seed_data import ensure_seed_data  # сиды
from routers import basic_router, profile_router, training_router  # <-- только эти

app = FastAPI()

# Healthcheck для Railway
@app.get("/health")
async def health():
    return {"status": "ok"}

# Инициализация бота и диспетчера
bot = Bot(settings.bot_token)
dp = Dispatcher()

# ВАЖНО: порядок
dp.include_router(profile_router)
dp.include_router(training_router)
dp.include_router(basic_router)

@app.on_event("startup")
async def on_startup():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")

    await init_db(settings.database_url)
    await ensure_seed_data()  # не забываем сиды

    await bot.delete_my_commands()
    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="Запуск бота / онбординг"),
            BotCommand(command="help", description="Справка по командам"),
            BotCommand(command="my_profile", description="Мой профиль"),
            BotCommand(command="train", description="Начать тренировку"),
        ]
    )

    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    await bot.set_webhook(settings.webhook_url, drop_pending_updates=True)


# Эндпоинт вебхука: путь берём из ENV через settings.webhook_path
@app.post(f"/{settings.webhook_path.strip('/')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}
