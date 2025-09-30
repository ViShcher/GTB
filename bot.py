import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from routers import basic_router, workouts_router
from config import settings
from db import init_db


bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


dp.include_router(basic_router)
dp.include_router(workouts_router)


async def on_startup():
await init_db(settings.database_url)


async def set_webhook():
# Установим вебхук на текущий домен Railway
await bot.set_webhook(settings.webhook_url, drop_pending_updates=True)


async def main_polling():
# вариант на всякий: локально можно запускать polling
await on_startup()
await dp.start_polling(bot)


if __name__ == "__main__":
asyncio.run(main_polling())
