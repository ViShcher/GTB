import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv

# Загружаем .env локально (на Pella переменные берутся из настроек проекта)
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN. Задай переменную окружения BOT_TOKEN.")

# Логи — чтобы видеть всё в хостинге
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я твой фитнес-бот 💪\n"
        "Команды:\n"
        "/start — приветствие\n"
        "/ping — проверка связи"
    )

@dp.message_handler(commands=["ping"])
async def cmd_ping(message: types.Message):
    await message.answer("pong 🏓")

# Страховка: снимаем возможный вебхук и очищаем очередь апдейтов
async def on_startup(dp):
    logger.info("Starting up: deleting webhook & dropping pending updates...")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Startup completed.")

async def on_shutdown(dp):
    logger.info("Shutting down...")

if __name__ == "__main__":
    # skip_updates=False — мы уже дропнули их в on_startup
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=False)
