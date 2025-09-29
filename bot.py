import logging, os
from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN. Укажи его в .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start', 'help'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Я твой фитнес-бот 💪\n"
        "Команды:\n"
        "/start — приветствие\n"
        "/ping — проверка связи"
    )

@dp.message_handler(commands=['ping'])
async def ping(message: types.Message):
    await message.answer("pong 🏓")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
