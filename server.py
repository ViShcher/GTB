import asyncio
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from config import settings
from db import init_db
from routers import basic_router, workouts_router


app = FastAPI()


# Healthcheck для Railway
@app.get("/health")
async def health():
return {"status": "ok"}


# Инициализация бота и диспетчера
bot = Bot(settings.bot_token)
dp = Dispatcher()
dp.include_router(basic_router)
dp.include_router(workouts_router)


@app.on_event("startup")
async def on_startup():
await init_db(settings.database_url)
# Ставим вебхук под текущий домен
if not settings.bot_token:
raise RuntimeError("BOT_TOKEN не задан")
await bot.set_webhook(settings.webhook_url, drop_pending_updates=True)


@app.post(f"/{settings.webhook_secret_path}")
async def telegram_webhook(request: Request):
try:
data = await request.json()
except Exception as e:
raise HTTPException(status_code=400, detail=str(e))


update = Update.model_validate(data)
await dp.feed_update(bot, update)
return {"ok": True}
