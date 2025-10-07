from __future__ import annotations

from datetime import datetime
from typing import Optional, List

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
        res = await session.exec(select(MuscleGroup).order_by(MuscleGroup.name))
        return res.all()


async def _fetch_exercises(group_id: Optional[int], page: int = 0, per_page: int = 10):
    async with await get_session(settings.database_url) as session:
        if group_id is None:
            total = (await session.exec(select(Exercise))).all()
            total_n = len(total)
            res = await session.exec(
                select(Exercise).order_by(Exercise.id.desc()).offset(page * per_page).limit(per_page)
            )
        else:
            base = select(Exercise).where(Exercise.primary_muscle_id == group_id)
            total_n = len((await session.exec(base)).all())
            res = await session.exec(base.order_by(Exercise.id.desc()).offset(page * per_page).limit(per_page))
        items = res.all()
        return items, total_n


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
        f"Сохранённых подходов: <b>{saved_sets}</b>\n"
        "Настрой кнопками ниже и нажми «Сохранить подход»."
    )


# ===================== Клавиатуры =====================
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
    rows.append([InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _exercise_buttons(exercises: List[Exercise], page: int, total: int, group_id: Optional[int]) -> InlineKeyboardMarkup:
    rows = []
    for ex in exercises:
        rows.append([InlineKeyboardButton(text=ex.name, callback_data=f"ex:{ex.id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="« Назад", callback_data=f"page:{group_id or 'all'}:{page-1}"))
    if (page + 1) * 10 < total:
        nav.append(InlineKeyboardButton(text="Далее »", callback_data=f"page:{group_id or 'all'}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton(text="↩ Выбрать группу", callback_data="back:groups"),
        InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _set_card_kb(reps: int, weight: float) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="−5", callback_data="rep:-:5"),
            InlineKeyboardButton(text="−2", callback_data="rep:-:2"),
            InlineKeyboardButton(text="−1", callback_data="rep:-:1"),
            InlineKeyboardButton(text="+1", callback_data="rep:+:1"),
            InlineKeyboardButton(text="+2", callback_data="rep:+:2"),
            InlineKeyboardButton(text="+5", callback_data="rep:+:5"),
        ],
        [
            InlineKeyboardButton(text="−10 кг", callback_data="wt:-:10"),
            InlineKeyboardButton(text="−5 кг", callback_data="wt:-:5"),
            InlineKeyboardButton(text="−2.5 кг", callback_data="wt:-:2.5"),
            InlineKeyboardButton(text="+2.5 кг", callback_data="wt:+:2.5"),
            InlineKeyboardButton(text="+5 кг", callback_data="wt:+:5"),
            InlineKeyboardButton(text="+10 кг", callback_data="wt:+:10"),
        ],
        [
            InlineKeyboardButton(text="⚡ Набор веса", callback_data="pick:weight"),
            InlineKeyboardButton(text="⚡ Набор повторов", callback_data="pick:reps"),
        ],
        [InlineKeyboardButton(text="✅ Сохранить подход", callback_data="save")],
        [
            InlineKeyboardButton(text="➕ Следующее упражнение", callback_data="back:exercises"),
            InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _weight_picker_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="2.5", callback_data="wp:+:2.5"),
         InlineKeyboardButton(text="5", callback_data="wp:+:5"),
         InlineKeyboardButton(text="10", callback_data="wp:+:10")],
        [InlineKeyboardButton(text="−2.5", callback_data="wp:-:2.5"),
         InlineKeyboardButton(text="−5", callback_data="wp:-:5"),
         InlineKeyboardButton(text="−10", callback_data="wp:-:10")],
        [InlineKeyboardButton(text="Очистить", callback_data="wp:clr"),
         InlineKeyboardButton(text="Применить", callback_data="wp:ok"),
         InlineKeyboardButton(text="← Назад", callback_data="wp:back")],
    ])


def _reps_picker_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="+1", callback_data="rp:+:1"),
         InlineKeyboardButton(text="+2", callback_data="rp:+:2"),
         InlineKeyboardButton(text="+5", callback_data="rp:+:5")],
        [InlineKeyboardButton(text="−1", callback_data="rp:-:1"),
         InlineKeyboardButton(text="−2", callback_data="rp:-:2"),
         InlineKeyboardButton(text="−5", callback_data="rp:-:5")],
        [InlineKeyboardButton(text="Очистить", callback_data="rp:clr"),
         InlineKeyboardButton(text="Применить", callback_data="rp:ok"),
         InlineKeyboardButton(text="← Назад", callback_data="rp:back")],
    ])


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


@training_router.callback_query(F.data.startswith("ex:"), Training.choose_exercise)
async def pick_exercise(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    ex_id = int(cb.data.split(":", 1)[1])
    data = await state.get_data()
    workout_id = int(data["workout_id"])
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, ex_id)
    reps, weight = 10, 0.0
    saved = await _count_sets(workout_id, ex_id)
    await state.update_data(ex_id=ex_id, reps=reps, weight=weight)
    await safe_edit_text(
        cb.message,
        _set_card_text(ex, reps, weight, saved_sets=saved),
        reply_markup=_set_card_kb(reps, weight),
    )
    await state.set_state(Training.log_set)


# ---------- быстрый набор веса ----------
@training_router.callback_query(F.data == "pick:weight", Training.log_set)
async def open_weight_picker(cb, state):
    await cb.answer()
    data = await state.get_data()
    await state.update_data(_tmp_weight=float(data.get("weight", 0.0)))
    await safe_edit_text(cb.message, "⚡ Быстрый набор веса:", reply_markup=_weight_picker_kb())


@training_router.callback_query(F.data.startswith("wp:"), Training.log_set)
async def weight_picker_actions(cb, state):
    parts = cb.data.split(":")
    action = parts[1]
    data = await state.get_data()
    cur = float(data.get("_tmp_weight", data.get("weight", 0.0)))

    if action in {"+", "-"}:
        step = float(parts[2])
        cur = max(0.0, cur + (step if action == "+" else -step))
        await state.update_data(_tmp_weight=round(cur, 1))
        await cb.answer(f"текущее: {cur:.1f} кг")
        return

    if action == "clr":
        await state.update_data(_tmp_weight=0.0)
        await cb.answer("текущее: 0.0 кг")
        return

    if action == "ok":
        reps = int(data.get("reps", 10))
        weight = float(data.get("_tmp_weight", cur))
        await state.update_data(weight=round(weight, 1))
        async with await get_session(settings.database_url) as session:
            ex = await session.get(Exercise, data["ex_id"])
        saved = await _count_sets(int(data["workout_id"]), int(data["ex_id"]))
        await safe_edit_text(
            cb.message,
            _set_card_text(ex, reps, weight, saved_sets=saved),
            reply_markup=_set_card_kb(reps, weight),
        )
        await cb.answer("Применено")
        return

    if action == "back":
        reps = int(data.get("reps", 10))
        weight = float(data.get("weight", 0.0))
        async with await get_session(settings.database_url) as session:
            ex = await session.get(Exercise, data["ex_id"])
        saved = await _count_sets(int(data["workout_id"]), int(data["ex_id"]))
        await safe_edit_text(
            cb.message,
            _set_card_text(ex, reps, weight, saved_sets=saved),
            reply_markup=_set_card_kb(reps, weight),
        )
        await cb.answer()


# ---------- быстрый набор повторов ----------
@training_router.callback_query(F.data == "pick:reps", Training.log_set)
async def open_reps_picker(cb, state):
    await cb.answer()
    data = await state.get_data()
    await state.update_data(_tmp_reps=int(data.get("reps", 10)))
    await safe_edit_text(cb.message, "⚡ Быстрый набор повторов:", reply_markup=_reps_picker_kb())


@training_router.callback_query(F.data.startswith("rp:"), Training.log_set)
async def reps_picker_actions(cb, state):
    parts = cb.data.split(":")
    action = parts[1]
    data = await state.get_data()
    cur = int(data.get("_tmp_reps", data.get("reps", 10)))

    if action in {"+", "-"}:
        step = int(parts[2])
        cur = max(1, cur + (step if action == "+" else -step))
        await state.update_data(_tmp_reps=cur)
        await cb.answer(f"текущее: {cur} повт.")
        return

    if action == "clr":
        await state.update_data(_tmp_reps=1)
        await cb.answer("текущее: 1 повт.")
        return

    if action == "ok":
        reps = int(data.get("_tmp_reps", cur))
        weight = float(data.get("weight", 0.0))
        await state.update_data(reps=reps)
        async with await get_session(settings.database_url) as session:
            ex = await session.get(Exercise, data["ex_id"])
        saved = await _count_sets(int(data["workout_id"]), int(data["ex_id"]))
        await safe_edit_text(
            cb.message,
            _set_card_text(ex, reps, weight, saved_sets=saved),
            reply_markup=_set_card_kb(reps, weight),
        )
        await cb.answer("Применено")
        return

    if action == "back":
        reps = int(data.get("reps", 10))
        weight = float(data.get("weight", 0.0))
        async with await get_session(settings.database_url) as session:
            ex = await session.get(Exercise, data["ex_id"])
        saved = await _count_sets(int(data["workout_id"]), int(data["ex_id"]))
        await safe_edit_text(
            cb.message,
            _set_card_text(ex, reps, weight, saved_sets=saved),
            reply_markup=_set_card_kb(reps, weight),
        )
        await cb.answer()


# ---------- сохранить подход ----------
@training_router.callback_query(F.data == "save", Training.log_set)
async def save_set(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Сохраняю…")
    data = await state.get_data()
    workout_id = int(data["workout_id"])
    ex_id = int(data["ex_id"])
    reps = int(data.get("reps", 10))
    weight = float(data.get("weight", 0.0))

    async with await get_session(settings.database_url) as session:
        item = WorkoutItem(
            workout_id=workout_id,
            exercise_id=ex_id,
            sets=1,
            reps=reps,
            weight=weight,
        )
        session.add(item)
        await session.commit()
        ex = await session.get(Exercise, ex_id)

    saved = await _count_sets(workout_id, ex_id)
    await safe_edit_text(
        cb.message,
        f"✅ Сохранено: <b>{_exercise_title(ex)}</b>\n"
        f"Подход: {reps} x {weight:.1f} кг\n"
        f"Сохранённых подходов: <b>{saved}</b>\n\n"
        "Можешь добавить ещё один подход или выбрать другое упражнение.",
        reply_markup=_set_card_kb(reps, weight),
    )


# ---------- вернуться к списку упражнений ----------
@training_router.callback_query(F.data == "back:exercises", Training.log_set)
async def back_to_exercises(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    group_id = data.get("group_id")
    page = int(data.get("ex_page", 0))
    exercises, total = await _fetch_exercises(group_id, page=page)
    await safe_edit_text(
        cb.message,
        "Выбери упражнение:",
        reply_markup=_exercise_buttons(exercises, page=page, total=total, group_id=group_id),
    )
    await state.set_state(Training.choose_exercise)


# ---------- завершить ----------
@training_router.callback_query(F.data == "finish")
async def finish_training(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Завершаем…")
    data = await state.get_data()
    workout_id = int(data.get("workout_id") or 0)
    await state.clear()

    if not workout_id:
        await safe_edit_text(cb.message, "Тренировка завершена.")
        return

    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(WorkoutItem).where(WorkoutItem.workout_id == workout_id))
        items = res.all()

    if not items:
        await safe_edit_text(cb.message, "Тренировка завершена. Сегодня подходов не сохранено.")
        return

    total_sets = len(items)
    total_weight = sum((it.reps or 0) * (it.weight or 0.0) for it in items)

    text = (
        "🏁 Тренировка завершена.\n"
        f"Подходов: <b>{total_sets}</b>\n"
        f"Поднятый вес: <b>{total_weight:.1f} кг</b>\n"
        "Сохранил. Возвращайся в меню."
    )
    await safe_edit_text(cb.message, text)
