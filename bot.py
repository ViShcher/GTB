
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import settings
from db import init_db
from routers import basic_router, profile_router, training_router

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# порядок тот же, чтобы /start не перехватывался
dp.include_router(profile_router)
dp.include_router(training_router)
dp.include_router(basic_router)

async def main():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан")
    await init_db(settings.database_url)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
