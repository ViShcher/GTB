from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from config import settings
from db import init_db
from routers import basic_router, workouts_router

from aiogram.types import BotCommand
from aiogram.types.bot_command_scope import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
)

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

bot = Bot(settings.bot_token)
dp = Dispatcher()
dp.include_router(basic_router)
dp.include_router(workouts_router)

@app.on_event("startup")
async def on_startup():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")

    await init_db(settings.database_url)

    # Переустанавливаем команды (перетираем старые)
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())

    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="Запуск бота"),
            BotCommand(command="help", description="Справка по командам"),
            BotCommand(command="add_ex", description="Добавить упражнение"),
            BotCommand(command="list_ex", description="Список упражнений"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )

    # Вебхук как и раньше
    await bot.set_webhook(settings.webhook_url, drop_pending_updates=True)
    
# Вариант 1: фиксированный путь из настроек
@app.post(f"/{settings.webhook_path.strip('/')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}
