from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

basic_router = Router()

@basic_router.message(CommandStart())
async def start(msg: Message):
    await msg.answer("Привет. Живу на вебхуке v3, всё слышу. Команды: /help, /add_ex name, /list_ex")

@basic_router.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer("Доступно: /add_ex <название> — добавить упражнение; /list_ex — список")
