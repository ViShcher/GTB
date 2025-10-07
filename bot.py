import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from routers import basic_router, profile_router, training_router
from config import settings
from db import init_db
from routers import basic_router, profile_router, training_router

bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# порядок тот же, чтобы /start не перехватывался
dp.include_router(profile_router)
dp.include_router(training_router)
dp.include_router(basic_router)

async def on_startup():
async def main():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")
    await init_db(settings.database_url)

async def main_polling():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main_polling())
    asyncio.run(main())
