from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from config import settings
from db import init_db
from routers import basic_router, workouts_router

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
