from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardRemove

basic_router = Router()

@basic_router.message(CommandStart())
async def start(msg: Message):
    # снимаем старую клавиатуру, если клиент её кэшировал
    await msg.answer(
        "Привет. Живу на вебхуке v3, всё слышу. Команды: /help, /add_ex name, /list_ex",
        reply_markup=ReplyKeyboardRemove()
    )

@basic_router.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer("Доступно: /add_ex <название> — добавить упражнение; /list_ex — список")

@basic_router.message(Command("reset_ui"))
async def reset_ui(msg: Message):
    await msg.answer("UI сброшен. Клавиатура убрана, команды обновлены.", reply_markup=ReplyKeyboardRemove())
