from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlmodel import select


from db import Exercise, get_session
from config import settings


workouts_router = Router()


@workouts_router.message(Command("add_ex"))
async def add_exercise(msg: Message):
name = msg.text.split(maxsplit=1)
if len(name) < 2:
await msg.answer("Укажи имя упражнения: /add_ex Жим лёжа")
return
ex_name = name[1].strip()


async with await get_session(settings.database_url) as session:
ex = Exercise(name=ex_name, type="strength")
session.add(ex)
await session.commit()


await msg.answer(f"Добавил упражнение: {ex_name}")


@workouts_router.message(Command("list_ex"))
async def list_exercises(msg: Message):
async with await get_session(settings.database_url) as session:
res = await session.exec(select(Exercise).order_by(Exercise.id.desc()).limit(20))
items = res.all()
if not items:
await msg.answer("Пусто. Добавь что-нибудь через /add_ex")
return
text = "\n".join([f"{e.id}. {e.name} [{e.type}]" for e in items])
await msg.answer(text)
