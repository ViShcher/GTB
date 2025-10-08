# routers/training.py — совместимо с текущей схемой БД (db.py из дампа 87)
# Силовые тренировки: выбор группы, упражнений, логирование подходов, итог

from __future__ import annotations

from datetime import datetime
from typing import Optional, Iterable, List

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlmodel import select
from sqlalchemy import func

from config import settings
from db import get_session, User, Workout, WorkoutItem, Exercise, MuscleGroup

training_router = Router()


# ===================== Состояния =====================
class Training(StatesGroup):
    choose_group = State()
    choose_exercise = State()
    log_set = State()  # ввод "вес повторы" для выбранного упражнения


# ===================== Вспомогательные =====================
async def _get_user(tg_id: int) -> Optional[User]:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        return res.first()

async def _create_workout_for_user(tg_id: int) -> int:
    """Всегда создаём новую тренировку (как в cardio), возвращаем workout.id"""
    async with await get_session(settings.database_url) as session:
        u = await session.exec(select(User).where(User.tg_id == tg_id))
        user = u.first()
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
        res = await session.exec(select(MuscleGroup).where(MuscleGroup.slug != "cardio"))
        return res.all()

async def _fetch_exercises(group_id: Optional[int], page: int = 0, per_page: int = 20) -> tuple[list[Exercise], int]:
    async with await get_session(settings.database_url) as session:
        base = select(Exercise).where(Exercise.type == "strength")
        if group_id:
            base = base.where(Exercise.primary_muscle_id == group_id)

        cnt = (await session.exec(select(func.count()).select_from(base.subquery()))).one() or 0
        res = await session.exec(
            base.order_by(Exercise.name.asc()).offset(page * per_page).limit(per_page)
        )
        return res.all(), int(cnt)

def _chunk(it: Iterable, n: int) -> list[list]:
    row, rows = [], []
    for x in it:
        row.append(x)
        if len(row) == n:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows

def _groups_kb(groups: list[MuscleGroup]) -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(text=g.name, callback_data=f"grp:{g.id}") for g in groups]
    rows = _chunk(btns, 2)  # две кнопки в ряд
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _exercises_kb(exercises: list[Exercise]) -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(text=e.name, callback_data=f"ex:{e.id}") for e in exercises]
    rows = _chunk(btns, 2)
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back:groups"),
        InlineKeyboardButton(text="🏁 Завершить", callback_data="finish"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _finish_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить подход", callback_data="noop")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:groups"),
         InlineKeyboardButton(text="🏁 Завершить", callback_data="finish")],
    ])

async def _exercise_name(ex_id: int) -> str:
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, ex_id)
    return ex.name if ex else "Упражнение"

async def _workout_totals(workout_id: int) -> tuple[int, float]:
    """Подсчёт итогов для силовых: число подходов и тоннаж (вес*повторы)"""
    async with await get_session(settings.database_url) as session:
        # считаем только записи с повторениями и весом
        q_sets = select(func.count()).where(
            WorkoutItem.workout_id == workout_id,
            WorkoutItem.reps.is_not(None),
            WorkoutItem.weight.is_not(None),
        )
        sets_cnt = (await session.exec(q_sets)).one() or 0

        q_ton = select(func.coalesce(func.sum(WorkoutItem.weight * WorkoutItem.reps), 0)).where(
            WorkoutItem.workout_id == workout_id,
            WorkoutItem.reps.is_not(None),
            WorkoutItem.weight.is_not(None),
        )
        ton = (await session.exec(q_ton)).one() or 0
    return int(sets_cnt), float(ton)


# ===================== Старт силовой =====================
@training_router.message(F.text == "🏋️ Тренировка")
async def start_training(msg: Message, state: FSMContext):
    user = await _get_user(msg.from_user.id)
    if not user or not all([user.gender, user.weight_kg, user.height_cm, user.age]):
        await msg.answer("Сначала /start и заполни профиль. Это займёт минуту, переживёшь.")
        return

    workout_id = await _create_workout_for_user(msg.from_user.id)
    await state.clear()
    await state.update_data(workout_id=workout_id)

    groups = await _fetch_groups()
    if not groups:
        await msg.answer("Справочник групп пуст. Добавь группы в БД и вернись.")
        return

    await msg.answer("Выбери группу мышц:", reply_markup=_groups_kb(groups))
    await state.set_state(Training.choose_group)


# ===================== Выбор группы =====================
@training_router.callback_query(F.data.startswith("grp:"), Training.choose_group)
async def pick_group(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    group_id = int(cb.data.split(":", 1)[1])

    exs, total = await _fetch_exercises(group_id)
    if not exs:
        await cb.message.edit_text("В этой группе пока нет упражнений. Выбери другую.")
        return

    await cb.message.edit_text(f"Выбери упражнение ({total} найдено):", reply_markup=_exercises_kb(exs))
    await state.update_data(group_id=group_id)
    await state.set_state(Training.choose_exercise)


# ===================== Назад к группам =====================
@training_router.callback_query(F.data == "back:groups")
async def back_groups(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    groups = await _fetch_groups()
    await cb.message.edit_text("Выбери группу мышц:", reply_markup=_groups_kb(groups))
    await state.set_state(Training.choose_group)


# ===================== Выбор упражнения =====================
@training_router.callback_query(F.data.startswith("ex:"), Training.choose_exercise)
async def pick_exercise(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    exercise_id = int(cb.data.split(":", 1)[1])
    await state.update_data(exercise_id=exercise_id)

    name = await _exercise_name(exercise_id)
    text = (
        f"🏋️ <b>{name}</b>\n\n"
        "Введи подход в формате:\n"
        "<code>вес повторы</code>\n"
        "например <code>75 10</code>\n\n"
        "Можно вводить подряд несколько сообщений."
    )
    await cb.message.edit_text(text, reply_markup=_finish_kb(), parse_mode="HTML")
    await state.set_state(Training.log_set)


# ===================== Ввод подхода (ручной) =====================
@training_router.message(Training.log_set)
async def log_set(msg: Message, state: FSMContext):
    raw = (msg.text or "").strip().replace(",", ".")
    parts = raw.split()
    if len(parts) != 2:
        await msg.answer("Формат: <b>вес повторы</b> (пример: <code>75 10</code>)", parse_mode="HTML")
        return

    try:
        weight = float(parts[0])
        reps = int(parts[1])
    except ValueError:
        await msg.answer("Не похоже на числа. Пример: <code>60 12</code>", parse_mode="HTML")
        return

    if weight <= 0 or reps <= 0:
        await msg.answer("Нужны положительные значения. Пример: <code>40 8</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    workout_id = int(data.get("workout_id", 0))
    exercise_id = int(data.get("exercise_id", 0))
    if not workout_id or not exercise_id:
        await msg.answer("Сессия потерялась. Нажми «🏋️ Тренировка» заново.")
        await state.clear()
        return

    async with await get_session(settings.database_url) as session:
        item = WorkoutItem(
            workout_id=workout_id,
            exercise_id=exercise_id,
            weight=weight,
            reps=reps,
            created_at=datetime.utcnow(),
        )
        session.add(item)
        await session.commit()

        ex = await session.get(Exercise, exercise_id)

    await msg.answer(f"✅ Сохранено: {ex.name} — {weight:.1f} кг × {reps}")

    # подсказка на следующий ввод
    await msg.answer("Введи следующий подход или нажми «🏁 Завершить».", reply_markup=_finish_kb())


# ===================== Завершить тренировку =====================
@training_router.callback_query(F.data == "finish")
async def finish_training(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    workout_id = int(data.get("workout_id", 0))

    # если FSM потерялось, возьмём самую свежую тренировку пользователя
    if not workout_id:
        async with await get_session(settings.database_url) as session:
            res = await session.exec(
                select(Workout)
                .join(User, User.id == Workout.user_id)
                .where(User.tg_id == cb.from_user.id)
                .order_by(Workout.created_at.desc())
                .limit(1)
            )
            w = res.first()
            workout_id = w.id if w else 0

    if not workout_id:
        await cb.message.edit_text("Активной тренировки не найдено. Нажми «🏋️ Тренировка».")
        await state.clear()
        return

    sets_cnt, ton = await _workout_totals(workout_id)
    await cb.message.edit_text(
        "🏁 Тренировка завершена!\n"
        f"Подходов: <b>{sets_cnt}</b>\n"
        f"Общий тоннаж: <b>{int(ton)} кг</b>",
        parse_mode="HTML",
    )
    await state.clear()
