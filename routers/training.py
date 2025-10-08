from __future__ import annotations

from datetime import datetime
from typing import Optional, List
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest
from sqlmodel import select, func

from config import settings
from db import get_session, User, Workout, WorkoutItem, Exercise, MuscleGroup

training_router = Router()


# ===================== FSM =====================
class Training(StatesGroup):
    choose_group = State()
    choose_exercise = State()
    log_set = State()


# ===================== Утилиты =====================
async def safe_edit_text(msg, text: str, **kwargs):
    """edit_text, который игнорирует 'message is not modified'."""
    try:
        return await msg.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


async def _get_user(tg_id: int) -> Optional[User]:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        return res.first()


async def _start_new_workout(tg_id: int) -> int:
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


async def _fetch_groups() -> List[MuscleGroup]:
    async with await get_session(settings.database_url) as session:
        # В силовом сценарии группу "Кардио" не показываем
        res = await session.exec(
            select(MuscleGroup)
            .where(MuscleGroup.slug != "cardio")
            .order_by(MuscleGroup.name)
        )
        return res.all()


from sqlalchemy import func

async def _fetch_exercises(group_id: Optional[int], page: int = 0, per_page: int = 10):
    async with await get_session(settings.database_url) as session:
        base_query = select(Exercise).where(Exercise.type == "strength")
        if group_id is not None:
            base_query = base_query.where(Exercise.primary_muscle_id == group_id)

        # считаем количество
        count_query = select(func.count()).select_from(base_query.subquery())
        total_n = (await session.exec(count_query)).one() or 0

        # выбираем страницу
        items = (
            (await session.exec(
                base_query.order_by(Exercise.name.asc())
                .offset(page * per_page)
                .limit(per_page)
            )).all()
        )

        return items, int(total_n)


async def _count_sets(workout_id: int, exercise_id: int) -> int:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(
            select(func.count(WorkoutItem.id)).where(
                WorkoutItem.workout_id == workout_id,
                WorkoutItem.exercise_id == exercise_id,
            )
        )
        return int(res.one())


def _exercise_title(ex: Exercise) -> str:
    return f"{ex.name} [{ex.type}]"


def _set_card_text(ex: Exercise, reps: int, weight: float, saved_sets: int) -> str:
    return (
        f"<b>{_exercise_title(ex)}</b>\n"
        f"Повторы: <b>{reps}</b>\n"
        f"Вес: <b>{weight:.1f} кг</b>\n"
        f"Сохранённых подходов: <b>{saved_sets}</b>\n\n"
        "Ручной ввод формата <b>вес повторы</b>. Примеры: <b>75 10</b>, <b>75/10</b>, <b>82.5x6</b>."
    )


# ===================== Клавиатуры =====================
def _exercise_buttons(
    exercises: List[Exercise], page: int, total: int, group_id: Optional[int]
) -> InlineKeyboardMarkup:
    rows = []
    for ex in exercises:
        rows.append([InlineKeyboardButton(text=ex.name, callback_data=f"ex:{ex.id}")])
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="« Назад", callback_data=f"page:{group_id or 'all'}:{page-1}"
            )
        )
    if (page + 1) * 10 < total:
        nav.append(
            InlineKeyboardButton(
                text="Далее »", callback_data=f"page:{group_id or 'all'}:{page+1}"
            )
        )
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="↩ Выбрать группу", callback_data="back:groups"),
            InlineKeyboardButton(
                text="🏁 Завершить тренировку", callback_data="finish"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _group_buttons(groups: List[MuscleGroup]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for g in groups:
        row.append(InlineKeyboardButton(text=g.name, callback_data=f"grp:{g.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _set_card_kb(reps: int, weight: float) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✅ Сохранить подход", callback_data="save")],
        [
            InlineKeyboardButton(
                text="➕ Следующее упражнение", callback_data="back:exercises"
            ),
            InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===================== Основные хэндлеры =====================
@training_router.message(Command("train"))
@training_router.message(F.text == "🏋️ Тренировка")
async def start_training(msg: Message, state: FSMContext):
    user = await _get_user(msg.from_user.id)
    if not user or not all([user.gender, user.weight_kg, user.height_cm, user.age]):
        await msg.answer("Сначала заполните профиль: нажмите /start и пройдите мини-мастер.")
        return
    workout_id = await _start_new_workout(msg.from_user.id)
    await state.clear()
    await state.update_data(workout_id=workout_id)
    groups = await _fetch_groups()
    await msg.answer("Выбери группу мышц:", reply_markup=_group_buttons(groups))
    await state.set_state(Training.choose_group)


@training_router.callback_query(F.data.startswith("grp:"), Training.choose_group)
async def choose_group(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    _, raw = cb.data.split(":", 1)
    group_id = None if raw == "all" else int(raw)
    exercises, total = await _fetch_exercises(group_id, page=0)
    await state.update_data(group_id=group_id, ex_page=0)
    await safe_edit_text(
        cb.message,
        "Выбери упражнение:",
        reply_markup=_exercise_buttons(exercises, page=0, total=total, group_id=group_id),
    )
    await state.set_state(Training.choose_exercise)


@training_router.callback_query(F.data == "back:groups", Training.choose_exercise)
@training_router.callback_query(F.data == "back:groups", Training.log_set)
async def back_to_groups(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    groups = await _fetch_groups()
    await safe_edit_text(cb.message, "Выбери группу мышц:", reply_markup=_group_buttons(groups))
    await state.set_state(Training.choose_group)
