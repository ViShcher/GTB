# bot.py — локальный запуск в режиме polling (отладка)
# Исправления: упрощённый старт, явная регистрация роутеров, фикс обработки callback_query 'choose_group_back'
from aiogram import Bot, Dispatcher, types
import asyncio
from routers import basic, workouts

TOKEN = "PUT_YOUR_TOKEN_HERE"

async def main():
    bot = Bot(TOKEN)
    dp = Dispatcher()
    basic.register(dp)
    workouts.register(dp)
    print("Bot for local polling started (debug).")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
