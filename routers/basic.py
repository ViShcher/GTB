# routers/basic.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove

basic_router = Router()

@basic_router.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "Доступно:\n"
        "/my_profile — посмотреть профиль\n"
        "Или жми кнопки главного меню.",
        reply_markup=ReplyKeyboardRemove()
    )

@basic_router.message(Command("reset_ui"))
async def reset_ui(msg: Message):
    await msg.answer("UI сброшен. Клавиатура убрана, команды обновлены.", reply_markup=ReplyKeyboardRemove())
