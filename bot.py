from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from routers import basic_router, profile_router, training_router
from config import settings
from db import init_db

bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(profile_router)
dp.include_router(training_router)
dp.include_router(basic_router)

async def on_startup():
    await init_db(settings.database_url)

async def main_polling():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main_polling())
