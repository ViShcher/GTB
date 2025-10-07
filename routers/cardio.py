
# routers/cardio.py
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from sqlmodel import select

from config import settings
from db import get_session, User, Workout, WorkoutItem, Exercise, MuscleGroup

cardio_router = Router()

# ===================== Состояния =====================
class Cardio(StatesGroup):
    choose_machine = State()
    input_metrics = State()

# ===================== Константы =====================
SKIPPING_NAME = "Скакалка"  # кардио, где вводим только время
DEFAULT_CARDIO = [
    ("Беговая дорожка", "treadmill"),
    ("Велотренажёр", "bike"),
    ("Эллиптический тренажёр", "elliptical"),
    ("Гребной тренажёр", "rower"),
    (SKIPPING_NAME, "jump_rope"),
]

# ===================== Утилиты БД =====================
async def _get_user(tg_id: int) -> Optional[User]:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        return res.first()

async def _get_or_create_workout(tg_id: int) -> int:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        user = res.first()
        if not user:
            raise RuntimeError("NO_USER")
        title = datetime.now().strftime("%Y-%m-%d %H:%M")
        w = Workout(user_id=user.id, title=title)
        session.add(w)
        await session.commit()
        await session.refresh(w)
        return w.id

async def _ensure_default_cardio():
    """Создаём кардио-упражнения по умолчанию (со slug и привязкой к группе 'cardio')."""
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(Exercise).where(Exercise.type == "cardio"))
        existing = res.all()
        have_slugs = {e.slug for e in existing if getattr(e, "slug", None)}

        # найдём id группы 'cardio' (по slug, на всякий случай — по имени)
        mg = await session.exec(select(MuscleGroup).where(MuscleGroup.slug == "cardio"))
        group = mg.first()
        if not group:
            mg = await session.exec(select(MuscleGroup).where(MuscleGroup.name == "Кардио"))
            group = mg.first()
        group_id = group.id if group else None

        to_add = []
        for name, slug in DEFAULT_CARDIO:
            if slug not in have_slugs:
                to_add.append(Exercise(name=name, slug=slug, type="cardio", primary_muscle_id=group_id))
        if to_add:
            for e in to_add:
                session.add(e)
            await session.commit()

async def _fetch_cardio_exercises(page: int = 0, per_page: int = 10):
    await _ensure_default_cardio()
    async with await get_session(settings.database_url) as session:
        base = select(Exercise).where(Exercise.type == "cardio")
        all_items = (await session.exec(base)).all()
        total = len(all_items)
        res = await session.exec(base.order_by(Exercise.name.asc()).offset(page * per_page).limit(per_page))
        items = res.all()
        return items, total

async def _count_saved(workout_id: int, exercise_id: int) -> int:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(
            select(WorkoutItem).where(
                WorkoutItem.workout_id == workout_id,
                WorkoutItem.exercise_id == exercise_id,
                WorkoutItem.duration_sec != None,  # noqa: E711
            )
        )
        return len(res.all())

# ===================== Вёрстка =====================
def _machines_kb(exercises: List[Exercise], page: int, total: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=ex.name, callback_data=f"cx:{ex.id}")] for ex in exercises]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="« Назад", callback_data=f"cpage:{page-1}"))
    if (page + 1) * 10 < total:
        nav.append(InlineKeyboardButton(text="Далее »", callback_data=f"cpage:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏁 Завершить кардио", callback_data="cfinish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _cardio_card_text(ex: Exercise, duration_min: Optional[int], distance_km: Optional[float], saved: int) -> str:
    dur_txt = f"{duration_min} мин" if duration_min else "—"
    dist_txt = f"{distance_km:.2f} км" if distance_km is not None else "—"
    base = (
        f"<b>{ex.name}</b> (кардио)\n"
        f"Время: <b>{dur_txt}</b>\n"
        f"Дистанция: <b>{dist_txt}</b>\n"
        f"Сохранённых записей: <b>{saved}</b>\n\n"
    )
    if ex.name == SKIPPING_NAME:
        hint = (
            "Введи результат в формате: <b>Время (мин)</b>\n"
            "Примеры: <code>10</code>, <code>15</code>, <code>25</code>\n"
            "Для скакалки дистанцию вводить не нужно."
        )
    else:
        hint = (
            "Введи результат в формате: <b>Время (мин), Дистанция (км)</b>\n"
            "Примеры: <code>30, 6.2</code>, <code>45/12</code>, <code>20 3</code>\n"
            "Можно указать только время: <code>25</code>."
        )
    return base + hint

def _cardio_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Сохранить", callback_data="csave"),
            InlineKeyboardButton(text="↩ Другая машина", callback_data="cback"),
            InlineKeyboardButton(text="🏁 Завершить", callback_data="cfinish"),
        ]]
    )

# ===================== Разбор ввода =====================
# Формат: "минуты[,/ пробел]километры?" где км опционально для всех, а для "Скакалка" игнорируется.
# Примеры: "30", "30, 6.2", "45/12", "20 3"
INPUT_RE = re.compile(r"^\s*(?P<min>\d+(?:[.,]\d+)?)\s*(?:[,/ ]\s*(?P<km>\d+(?:[.,]\d+)?))?\s*$")

def _norm_minutes(val: str) -> int:
    # Допускаем дробные минуты, округляем до целых
    minutes = float(val.replace(",", "."))
    return max(1, int(round(minutes)))

def _norm_km(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    return float(val.replace(",", "."))

# ===================== Команды/Хэндлеры =====================
@cardio_router.message(Command("cardio"))
@cardio_router.message(F.text == "🚴 Кардио")
async def start_cardio(msg: Message, state: FSMContext):
    user = await _get_user(msg.from_user.id)
    if not user or not all([user.gender, user.weight_kg, user.height_cm, user.age]):
        await msg.answer("Сначала /start и заполни профиль. Это займёт минуту, не страдай.")
        return
    workout_id = await _get_or_create_workout(msg.from_user.id)
    await state.clear()
    await state.update_data(c_workout_id=workout_id, c_page=0)
    items, total = await _fetch_cardio_exercises(page=0)
    await msg.answer("Выбери тренажёр (кардио):", reply_markup=_machines_kb(items, page=0, total=total))
    await state.set_state(Cardio.choose_machine)

@cardio_router.callback_query(F.data.startswith("cpage:"), Cardio.choose_machine)
async def cardio_page(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    page = int(cb.data.split(":", 1)[1])
    await state.update_data(c_page=page)
    items, total = await _fetch_cardio_exercises(page=page)
    await cb.message.edit_text("Выбери тренажёр (кардио):", reply_markup=_machines_kb(items, page=page, total=total))

@cardio_router.callback_query(F.data.startswith("cx:"), Cardio.choose_machine)
async def pick_machine(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    ex_id = int(cb.data.split(":", 1)[1])
    data = await state.get_data()
    workout_id = int(data["c_workout_id"])
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, ex_id)
    saved = await _count_saved(workout_id, ex_id)
    await state.update_data(c_ex_id=ex_id, c_min=None, c_km=None, c_last_msg=cb.message.message_id)
    await cb.message.edit_text(
        _cardio_card_text(ex, None, None, saved),
        reply_markup=_cardio_kb(),
        parse_mode="HTML",
    )
    await state.set_state(Cardio.input_metrics)

@cardio_router.message(Cardio.input_metrics, F.text.regexp(INPUT_RE))
async def cardio_input(msg: Message, state: FSMContext):
    text = msg.text.strip()
    m = INPUT_RE.match(text)
    if not m:
        return
    minutes = _norm_minutes(m.group("min"))
    km = _norm_km(m.group("km"))

    data = await state.get_data()
    ex_id = int(data["c_ex_id"])
    workout_id = int(data["c_workout_id"])

    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, ex_id)

    # Для "Скакалка" игнорируем дистанцию
    distance_km = None if ex.name == SKIPPING_NAME else km

    await state.update_data(c_min=minutes, c_km=distance_km)
    saved = await _count_saved(workout_id, ex_id)

    try:
        await msg.bot.edit_message_text(
            chat_id=msg.chat.id,
            message_id=int(data.get("c_last_msg") or msg.message_id),
            text=_cardio_card_text(ex, minutes, distance_km, saved),
            reply_markup=_cardio_kb(),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await msg.answer(_cardio_card_text(ex, minutes, distance_km, saved), reply_markup=_cardio_kb())

@cardio_router.callback_query(F.data == "csave", Cardio.input_metrics)
async def cardio_save(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Сохраняю…")
    data = await state.get_data()
    ex_id = int(data["c_ex_id"])
    workout_id = int(data["c_workout_id"])
    minutes = int(data.get("c_min") or 0)
    km = data.get("c_km")
    if minutes <= 0:
        await cb.message.edit_text("Нужно указать время в минутах. Примеры: 10, 30, 45/12")
        return

    distance_m = int(round(float(km) * 1000)) if km is not None else None

    async with await get_session(settings.database_url) as session:
        item = WorkoutItem(
            workout_id=workout_id,
            exercise_id=ex_id,
            duration_sec=minutes * 60,
            distance_m=distance_m,
        )
        session.add(item)
        await session.commit()
        ex = await session.get(Exercise, ex_id)

    dist_txt = f"{km:.2f} км" if km is not None else "—"
    await cb.message.edit_text(
        f"✅ Сохранено: <b>{ex.name}</b>\n"
        f"Время: <b>{minutes} мин</b> | Дистанция: <b>{dist_txt}</b>\n"
        "Можешь ввести следующее значение или выбрать другой тренажёр.",
        reply_markup=_cardio_kb(),
        parse_mode="HTML",
    )

@cardio_router.callback_query(F.data == "cback", Cardio.input_metrics)
async def cardio_back(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    page = int((await state.get_data()).get("c_page", 0))
    items, total = await _fetch_cardio_exercises(page=page)
    await cb.message.edit_text("Выбери тренажёр (кардио):", reply_markup=_machines_kb(items, page=page, total=total))
    await state.set_state(Cardio.choose_machine)

@cardio_router.callback_query(F.data == "cfinish")
async def cardio_finish(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Готово")
    await state.clear()
    await cb.message.edit_text("Кардио завершено. Иди пей воду.")
