from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BotCommand, MenuButtonDefault
from aiogram.types.bot_command_scope import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
)

from config import settings
from db import init_db
from routers import basic_router, workouts_router, profile_router

app = FastAPI()

# Healthcheck для Railway
@app.get("/health")
async def health():
    return {"status": "ok"}

# Инициализация бота и диспетчера
bot = Bot(settings.bot_token)
dp = Dispatcher()
dp.include_router(profile_router)
dp.include_router(basic_router)
dp.include_router(workouts_router)

@app.on_event("startup")
async def on_startup():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")

    # Инициализация БД
    await init_db(settings.database_url)

    # ======== Блок установки команд ========
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())

    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="Запуск бота / онбординг"),
            BotCommand(command="help", description="Справка по командам"),
            BotCommand(command="my_profile", description="Мой профиль"),
            BotCommand(command="list_ex", description="Список упражнений"),
            BotCommand(command="add_ex", description="Добавить упражнение"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    # ======== Конец блока команд ========

    # Сброс кастомной кнопки меню на стандартную
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    # Установка вебхука на публичный домен Railway + путь из ENV (WEBHOOK_PATH)
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
