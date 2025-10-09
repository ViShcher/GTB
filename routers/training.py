# routers/training.py — финальная версия под текущую схему БД
# Силовые: группы → упражнения → ввод "вес повторы" / "вес/повторы" → счётчик → завершение

from __future__ import annotations

from datetime import datetime
from typing import Optional, Iterable, List
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlmodel import select
from sqlalchemy import func, case

from config import settings
from db import get_session, User, Workout, WorkoutItem, Exercise, MuscleGroup

training_router = Router()

# ========= FSM =========
class Training(StatesGroup):
    choose_group = State()
    choose_exercise = State()
    log_set = State()  # ввод подходов для выбранного упражнения

# ========= Парсер ввода =========
# Разделитель между весом и повторами: пробел или "/" (НЕ запятая/точка, они допустимы только ВНУТРИ веса)
STRENGTH_INPUT_RE = re.compile(
    r"^\s*(?P<kg>\d+(?:[.,]\d+)?)\s*(?:/|\s+)\s*(?P<reps>\d+)\s*$"
)

# ========= Утилиты =========
async def _get_user(tg_id: int) -> Optional[User]:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        return res.first()

async def _create_workout_for_user(tg_id: int) -> int:
    """Создаём новую силовую тренировку (как в кардио) и возвращаем ID."""
    async with await get_session(settings.database_url) as session:
        u = await session.exec(select(User).where(User.tg_id == tg_id))
        user = u.first()
        if not user:
            raise RuntimeError("NO_USER")
        title = datetime.now().strftime("%Y-%m-%d %H:%M")
        w = Workout(user_id=user.id, title=title)  # created_at ставится моделью
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

        count_query = select(func.count()).select_from(base.subquery())
        total = (await session.exec(count_query)).one() or 0

        res = await session.exec(
            base.order_by(Exercise.name.asc()).offset(page * per_page).limit(per_page)
        )
        return res.all(), int(total)

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
        InlineKeyboardButton(text="⬅️ Назад к группам", callback_data="back:groups"),
        InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="workout:finish"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _exercise_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к группам", callback_data="back:groups"),
         InlineKeyboardButton(text="✅ Завершить упражнение", callback_data="ex:finish")],
        [InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="workout:finish")],
    ])

async def _exercise_name(ex_id: int) -> str:
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, ex_id)
    return ex.name if ex else "Упражнение"

async def _count_sets_for_ex(workout_id: int, exercise_id: int) -> int:
    async with await get_session(settings.database_url) as session:
        q = select(func.count()).where(
            WorkoutItem.workout_id == workout_id,
            WorkoutItem.exercise_id == exercise_id,
            WorkoutItem.reps.is_not(None),
            WorkoutItem.weight.is_not(None),
        )
        return int((await session.exec(q)).one() or 0)

def _exercise_card_text(name: str, saved_sets: int) -> str:
    return (
        f"🏋️ <b>{name}</b>\n"
        f"Сохранённых подходов: <b>{saved_sets}</b>\n\n"
        "Введи подход в формате:\n"
        "<code>вес повторы</code> или <code>вес/повторы</code>\n"
        "Примеры: <code>75 10</code>, <code>80/8</code>, <code>112,5 5</code>, <code>24.5/8</code>\n\n"
        "Можно вводить подряд несколько сообщений."
    )

async def _workout_totals(workout_id: int) -> tuple[int, float]:
    """Итоги тренировки: число подходов и поднятый вес (гантельные ×2 по названию)."""
    async with await get_session(settings.database_url) as session:
        q_sets = select(func.count()).where(
            WorkoutItem.workout_id == workout_id,
            WorkoutItem.reps.is_not(None),
            WorkoutItem.weight.is_not(None),
        )
        sets_cnt = int((await session.exec(q_sets)).one() or 0)

        q_lifted = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (func.lower(Exercise.name).like("%гантел%"), 2),
                            else_=1,
                        ) * WorkoutItem.weight * WorkoutItem.reps
                    ),
                    0
                )
            )
            .join(Exercise, Exercise.id == WorkoutItem.exercise_id)
            .where(
                WorkoutItem.workout_id == workout_id,
                WorkoutItem.reps.is_not(None),
                WorkoutItem.weight.is_not(None),
            )
        )
        lifted = float((await session.exec(q_lifted)).one() or 0.0)

    return sets_cnt, lifted

async def safe_edit_text(message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")

# ========= Старт силовой =========
@training_router.message(F.text == "🏋️ Тренировка")
async def start_training(msg: Message, state: FSMContext):
    user = await _get_user(msg.from_user.id)
    if not user:
        await msg.answer("Сначала /start и заполни профиль. Это быстро.")
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

# ========= Выбор группы =========
@training_router.callback_query(F.data.startswith("grp:"), Training.choose_group)
async def pick_group(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    group_id = int(cb.data.split(":", 1)[1])
    await state.update_data(group_id=group_id)

    exs, total = await _fetch_exercises(group_id)
    if not exs:
        await safe_edit_text(cb.message, "В этой группе пока нет упражнений. Выбери другую.")
        return

    await safe_edit_text(cb.message, f"Выбери упражнение ({total} найдено):", reply_markup=_exercises_kb(exs))
    await state.set_state(Training.choose_exercise)

# ========= Назад к группам (из любых состояний силовой) =========
@training_router.callback_query(F.data == "back:groups")
async def back_groups(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    groups = await _fetch_groups()
    await safe_edit_text(cb.message, "Выбери группу мышц:", reply_markup=_groups_kb(groups))
    await state.set_state(Training.choose_group)

# ========= Выбор упражнения =========
@training_router.callback_query(F.data.startswith("ex:"), Training.choose_exercise)
async def pick_exercise(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    exercise_id = int(cb.data.split(":", 1)[1])
    await state.update_data(exercise_id=exercise_id)

    name = await _exercise_name(exercise_id)
    data = await state.get_data()
    workout_id = int(data.get("workout_id") or 0)
    saved = await _count_sets_for_ex(workout_id, exercise_id)

    await cb.message.edit_text(
        _exercise_card_text(name, saved),
        reply_markup=_exercise_panel_kb(),
        parse_mode="HTML"
    )

    # запомним id сообщения экрана упражнения, чтобы обновлять счётчик
    await state.update_data(s_last_msg=cb.message.message_id, s_ex_name=name)
    await state.set_state(Training.log_set)

# ========= Завершить упражнение (только возврат к списку) =========
@training_router.callback_query(F.data == "ex:finish", Training.log_set)
async def finish_exercise(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    group_id = int(data.get("group_id") or 0)
    if not group_id:
        groups = await _fetch_groups()
        await safe_edit_text(cb.message, "Выбери группу мышц:", reply_markup=_groups_kb(groups))
        await state.set_state(Training.choose_group)
        return

    exs, total = await _fetch_exercises(group_id)
    await safe_edit_text(cb.message, f"Выбери упражнение ({total} найдено):", reply_markup=_exercises_kb(exs))
    await state.set_state(Training.choose_exercise)

# ========= Ввод подхода =========
@training_router.message(Training.log_set)
async def log_set(msg: Message, state: FSMContext):
    raw = (msg.text or "").strip()
    m = STRENGTH_INPUT_RE.match(raw)
    if not m:
        await msg.answer(
            "Формат: <b>вес повторы</b> или <b>вес/повторы</b>\n"
            "Примеры: <code>75 10</code>, <code>80/8</code>, <code>112,5 5</code>, <code>24.5/8</code>",
            parse_mode="HTML",
        )
        return

    weight = float(m.group("kg").replace(",", "."))
    reps = int(m.group("reps"))
    if weight <= 0 or reps <= 0:
        await msg.answer("Нужны положительные значения. Пример: <code>40 8</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    workout_id = int(data.get("workout_id") or 0)
    exercise_id = int(data.get("exercise_id") or 0)
    last_msg_id = int(data.get("s_last_msg") or 0)
    ex_name = data.get("s_ex_name") or (await _exercise_name(exercise_id))

    # Автовосстановление workout_id, если пропал
    if not workout_id:
        async with await get_session(settings.database_url) as session:
            res = await session.exec(
                select(Workout)
                .join(User, User.id == Workout.user_id)
                .where(User.tg_id == msg.from_user.id)
                .order_by(Workout.created_at.desc())
                .limit(1)
            )
            last = res.first()
            if last:
                workout_id = last.id
                await state.update_data(workout_id=workout_id)

    if not exercise_id:
        await msg.answer("Не выбрано упражнение. Сначала нажми на упражнение в списке.")
        await state.set_state(Training.choose_exercise)
        return

    if not workout_id:
        await msg.answer("Сессия потерялась. Нажми «🏋️ Тренировка» заново.")
        await state.clear()
        return

    # Сохраняем подход
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

    # Обновляем счётчик на экране упражнения
    saved = await _count_sets_for_ex(workout_id, exercise_id)
    card_text = _exercise_card_text(ex_name, saved)

    try:
        await msg.bot.edit_message_text(
            chat_id=msg.chat.id,
            message_id=last_msg_id or msg.message_id,
            text=card_text,
            reply_markup=_exercise_panel_kb(),
            parse_mode="HTML",
        )
    except Exception:
        sent = await msg.answer(card_text, reply_markup=_exercise_panel_kb(), parse_mode="HTML")
        await state.update_data(s_last_msg=sent.message_id)

    # Подтверждение отдельным сообщением
    await msg.answer(f"✅ Сохранено: {ex_name} — {weight:.1f} кг × {reps}")

# ========= Завершить ВСЮ тренировку =========
@training_router.callback_query(F.data == "workout:finish")
async def workout_finish(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    workout_id = int(data.get("workout_id") or 0)

    # если потеряли id тренировки — найдём последнюю по пользователю
    if not workout_id:
        async with await get_session(settings.database_url) as session:
            res = await session.exec(
                select(Workout)
                .join(User, User.id == Workout.user_id)
                .where(User.tg_id == cb.from_user.id)
                .order_by(Workout.created_at.desc())
                .limit(1)
            )
            last = res.first()
            workout_id = last.id if last else 0

    if not workout_id:
        await safe_edit_text(cb.message, "Активной тренировки не найдено. Нажми «🏋️ Тренировка».")
        await state.clear()
        return

    sets_cnt, lifted = await _workout_totals(workout_id)
    await safe_edit_text(
        cb.message,
        "🏁 Тренировка завершена!\n"
        f"Подходов: <b>{sets_cnt}</b>\n"
        f"Поднятый вес: <b>{int(lifted)} кг</b>",
    )
    await state.clear()
