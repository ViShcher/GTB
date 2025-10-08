# routers/training.py — полная версия (2025-10-09)
# Силовые тренировки: выбор группы, упражнения и логирование подходов

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlmodel import select, func
from datetime import datetime

from config import settings
from db import get_session, Workout, WorkoutItem, Exercise, MuscleGroup, User

training_router = Router()


# ===== FSM =====
class Training(StatesGroup):
    choose_group = State()
    choose_exercise = State()
    log_set = State()


# ===== Вспомогательные функции =====
async def _fetch_groups():
    """Получаем группы мышц для выбора."""
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(MuscleGroup).where(MuscleGroup.slug != "cardio"))
        groups = res.all()
        return groups


async def _fetch_exercises(group_id: int | None, page: int = 0, per_page: int = 15):
    """Возвращает упражнения по группе."""
    async with await get_session(settings.database_url) as session:
        q = select(Exercise).where(Exercise.type == "strength")
        if group_id:
            q = q.where(Exercise.primary_muscle_id == group_id)
        count = await session.exec(select(func.count()).select_from(q.subquery()))
        total = count.one() or 0
        res = await session.exec(
            q.order_by(Exercise.name.asc())
             .offset(page * per_page)
             .limit(per_page)
        )
        return res.all(), int(total)


async def _get_or_create_workout(user_tg_id: int):
    """Возвращает текущую тренировку пользователя или создаёт новую."""
    async with await get_session(settings.database_url) as session:
        res = await session.exec(
            select(Workout)
            .where(Workout.user_tg_id == user_tg_id)
            .order_by(Workout.id.desc())
            .limit(1)
        )
        last = res.first()
        if last and not last.finished_at:
            return last

        new = Workout(user_tg_id=user_tg_id, started_at=datetime.utcnow())
        session.add(new)
        await session.commit()
        await session.refresh(new)
        return new


async def safe_edit_text(message, text: str, reply_markup=None):
    """Безопасно редактирует сообщение (если не изменилось)."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


# ===== Кнопки =====
def _group_buttons(groups):
    rows = []
    for g in groups:
        rows.append([InlineKeyboardButton(text=g.name, callback_data=f"group:{g.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _exercise_buttons(exercises):
    rows = []
    for e in exercises:
        rows.append([InlineKeyboardButton(text=e.name, callback_data=f"ex:{e.id}")])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back:groups"),
        InlineKeyboardButton(text="🏁 Завершить", callback_data="finish"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _finish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершить тренировку", callback_data="finish")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:groups")],
    ])


# ===== Команда /train =====
@training_router.message(F.text == "🏋️ Тренировка")
async def start_training(msg: Message, state: FSMContext):
    groups = await _fetch_groups()
    await msg.answer("Выбери группу мышц:", reply_markup=_group_buttons(groups))
    await state.set_state(Training.choose_group)


# ===== Выбор группы =====
@training_router.callback_query(F.data.startswith("group:"), Training.choose_group)
async def choose_group(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    group_id = int(cb.data.split(":")[1])
    exercises, total = await _fetch_exercises(group_id)
    if not exercises:
        await safe_edit_text(cb.message, "В этой группе пока нет упражнений.")
        return
    await safe_edit_text(
        cb.message,
        f"Выбери упражнение ({total} найдено):",
        reply_markup=_exercise_buttons(exercises),
    )
    await state.update_data(group_id=group_id)
    await state.set_state(Training.choose_exercise)


# ===== Назад к группам =====
@training_router.callback_query(F.data == "back:groups")
async def back_to_groups(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    groups = await _fetch_groups()
    await safe_edit_text(cb.message, "Выбери группу мышц:", reply_markup=_group_buttons(groups))
    await state.set_state(Training.choose_group)


# ===== Выбор упражнения =====
@training_router.callback_query(F.data.startswith("ex:"), Training.choose_exercise)
async def choose_exercise(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    exercise_id = int(cb.data.split(":")[1])

    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(Exercise).where(Exercise.id == exercise_id))
        exercise = res.first()

    if not exercise:
        await cb.message.answer("Ошибка: упражнение не найдено.")
        return

    workout = await _get_or_create_workout(cb.from_user.id)

    # обновим FSM
    await state.update_data(exercise_id=exercise.id, workout_id=workout.id)

    text = (
        f"🏋️ <b>{exercise.name}</b>\n\n"
        "Введи подход в формате:\n"
        "<code>вес повторы</code>\n"
        "например <code>75 10</code>"
    )
    await safe_edit_text(cb.message, text, reply_markup=_finish_kb())
    await state.set_state(Training.log_set)


# ===== Ввод подхода вручную =====
@training_router.message(Training.log_set)
async def manual_log_set(msg: Message, state: FSMContext):
    text = msg.text.strip()
    parts = text.replace(",", ".").split()
    if len(parts) != 2:
        await msg.answer("Формат должен быть: <b>вес повторы</b>\nНапример: 75 10")
        return

    try:
        weight = float(parts[0])
        reps = int(parts[1])
    except ValueError:
        await msg.answer("Некорректный ввод. Пример: 75 10")
        return

    data = await state.get_data()
    workout_id = data.get("workout_id")
    exercise_id = data.get("exercise_id")

    async with await get_session(settings.database_url) as session:
        item = WorkoutItem(
            workout_id=workout_id,
            exercise_id=exercise_id,
            weight=weight,
            reps=reps,
            logged_at=datetime.utcnow(),
        )
        session.add(item)
        await session.commit()

        res = await session.exec(select(Exercise).where(Exercise.id == exercise_id))
        ex = res.first()

    await msg.answer(f"✅ Сохранено: {ex.name} — {weight} кг × {reps} повторов")

    await msg.answer(
        "Введи следующий подход или заверши тренировку.",
        reply_markup=_finish_kb(),
    )


# ===== Завершить тренировку (универсально, из любого состояния) =====
from sqlalchemy import func

@training_router.callback_query(F.data == "finish")
async def finish_training(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    user_id = cb.from_user.id

    # Попробуем взять workout_id из FSM, если нет — найдём последнюю незавершённую
    data = await state.get_data()
    workout_id = data.get("workout_id")

    async with await get_session(settings.database_url) as session:
        workout = None

        if workout_id:
            res = await session.exec(select(Workout).where(Workout.id == workout_id))
            workout = res.first()

        if not workout:
            res = await session.exec(
                select(Workout)
                .where(Workout.user_tg_id == user_id, Workout.finished_at.is_(None))
                .order_by(Workout.id.desc())
                .limit(1)
            )
            workout = res.first()

        if not workout:
            await cb.message.answer("Активной тренировки нет. Начни с «🏋️ Тренировка».")
            await state.clear()
            return

        # Закрываем тренировку
        workout.finished_at = datetime.utcnow()
        await session.commit()

        # Итоги
        total_sets = (await session.exec(
            select(func.count()).where(WorkoutItem.workout_id == workout.id)
        )).one() or 0

        total_weight = (await session.exec(
            select(func.coalesce(func.sum(WorkoutItem.weight * WorkoutItem.reps), 0))
            .where(WorkoutItem.workout_id == workout.id)
        )).one() or 0

    await cb.message.answer(
        "🏁 Тренировка завершена!\n"
        f"Подходов: {total_sets}\n"
        f"Общий тоннаж: {int(total_weight)} кг"
    )
    await state.clear()
