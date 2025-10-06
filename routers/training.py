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

from sqlmodel import select

from config import settings
from db import get_session, User, Workout, WorkoutItem, Exercise, MuscleGroup

training_router = Router()


# ===================== FSM =====================
class Training(StatesGroup):
    choose_group = State()
    choose_exercise = State()
    log_set = State()


# ===================== Клавиатуры =====================
def _group_buttons(groups: List[MuscleGroup]) -> InlineKeyboardMarkup:
    # Если групп нет в БД — даём “Все упражнения”
    if not groups:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Все упражнения", callback_data="grp:all")],
            [InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish")],
        ])
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
    # репы: +/- 1, 2, 5; вес: +/- 2.5, 5, 10
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
            InlineKeyboardButton(text="✅ Сохранить подход", callback_data="save"),
        ],
        [
            InlineKeyboardButton(text="➕ Следующее упражнение", callback_data="back:exercises"),
            InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="finish"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===================== Утилиты =====================
async def _ensure_user_and_workout(tg_id: int) -> int:
    """Возвращает активный workout_id пользователя на сегодня, создаёт если нет."""
    async with await get_session(settings.database_url) as session:
        # User
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        user = res.first()
        if not user:
            # Ладно, если человек не проходил онбординг — создадим минимальную запись.
            user = User(tg_id=tg_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Workout на сегодня по пользователю (по простому — по дате)
        title = datetime.now().strftime("%Y-%m-%d")
        res = await session.exec(
            select(Workout).where(Workout.user_id == user.id, Workout.title == title)
        )
        w = res.first()
        if not w:
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
        if group_id is None:  # all
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


def _exercise_title(ex: Exercise) -> str:
    return f"{ex.name} [{ex.type}]"


def _set_card_text(ex: Exercise, reps: int, weight: float) -> str:
    return (
        f"<b>{_exercise_title(ex)}</b>\n"
        f"Повторы: <b>{reps}</b>\n"
        f"Вес: <b>{weight:.1f} кг</b>\n"
        "Настрой кнопками ниже и нажми «Сохранить подход»."
    )


# ===================== Точки входа =====================
@training_router.message(Command("train"))
@training_router.message(F.text == "🏋️ Тренировка")
async def start_training(msg: Message, state: FSMContext):
    await _ensure_user_and_workout(msg.from_user.id)
    groups = await _fetch_groups()
    await msg.answer(
        "Выбери группу мышц (или все упражнения):",
        reply_markup=_group_buttons(groups),
    )
    await state.set_state(Training.choose_group)


# ===================== Выбор группы / страница упражнений =====================
@training_router.callback_query(F.data.startswith("grp:"), Training.choose_group)
async def choose_group(cb: CallbackQuery, state: FSMContext):
    _, raw = cb.data.split(":", 1)
    group_id = None if raw == "all" else int(raw)
    exercises, total = await _fetch_exercises(group_id, page=0)
    await state.update_data(group_id=group_id, ex_page=0)
    if total == 0:
        await cb.answer("В этой группе пока пусто.", show_alert=True)
        return
    await cb.message.edit_text(
        "Выбери упражнение:",
        reply_markup=_exercise_buttons(exercises, page=0, total=total, group_id=group_id),
    )
    await state.set_state(Training.choose_exercise)
    await cb.answer()


@training_router.callback_query(F.data.startswith("page:"), Training.choose_exercise)
async def paginate_exercises(cb: CallbackQuery, state: FSMContext):
    _, group_raw, page_raw = cb.data.split(":", 2)
    group_id = None if group_raw == "all" else int(group_raw)
    page = int(page_raw)
    exercises, total = await _fetch_exercises(group_id, page=page)
    await state.update_data(group_id=group_id, ex_page=page)
    await cb.message.edit_reply_markup(
        reply_markup=_exercise_buttons(exercises, page=page, total=total, group_id=group_id)
    )
    await cb.answer()


@training_router.callback_query(F.data == "back:groups", Training.choose_exercise)
async def back_to_groups(cb: CallbackQuery, state: FSMContext):
    groups = await _fetch_groups()
    await cb.message.edit_text("Выбери группу мышц (или все упражнения):", reply_markup=_group_buttons(groups))
    await state.set_state(Training.choose_group)
    await cb.answer()


# ===================== Выбор упражнения / лог подхода =====================
@training_router.callback_query(F.data.startswith("ex:"), Training.choose_exercise)
async def pick_exercise(cb: CallbackQuery, state: FSMContext):
    ex_id = int(cb.data.split(":", 1)[1])
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, ex_id)
    if not ex:
        await cb.answer("Не нашёл упражнение", show_alert=True)
        return

    # Стартовые значения (можно подтягивать последние из истории позже)
    reps = 10
    weight = 0.0
    await state.update_data(ex_id=ex_id, reps=reps, weight=weight)

    await cb.message.edit_text(
        _set_card_text(ex, reps, weight),
        reply_markup=_set_card_kb(reps, weight),
    )
    await state.set_state(Training.log_set)
    await cb.answer()


@training_router.callback_query(F.data.startswith("rep:"), Training.log_set)
async def change_reps(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":", maxsplit=2)  # rep:+:2
    sign, step_raw = parts[1], parts[2]
    data = await state.get_data()
    reps = int(data.get("reps", 10))
    weight = float(data.get("weight", 0.0))
    step = int(float(step_raw))
    reps = max(1, reps + step if sign == "+" else reps - step)

    await state.update_data(reps=reps)
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, data["ex_id"])
    await cb.message.edit_text(_set_card_text(ex, reps, weight), reply_markup=_set_card_kb(reps, weight))
    await cb.answer()


@training_router.callback_query(F.data.startswith("wt:"), Training.log_set)
async def change_weight(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":", maxsplit=2)  # wt:+:2.5
    sign, step_raw = parts[1], parts[2]
    data = await state.get_data()
    reps = int(data.get("reps", 10))
    weight = float(data.get("weight", 0.0))
    step = float(step_raw)
    weight = max(0.0, weight + step if sign == "+" else weight - step)

    await state.update_data(weight=round(weight, 1))
    async with await get_session(settings.database_url) as session:
        ex = await session.get(Exercise, data["ex_id"])
    await cb.message.edit_text(_set_card_text(ex, reps, round(weight, 1)), reply_markup=_set_card_kb(reps, round(weight, 1)))
    await cb.answer()


@training_router.callback_query(F.data == "save", Training.log_set)
async def save_set(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ex_id = int(data["ex_id"])
    reps = int(data.get("reps", 10))
    weight = float(data.get("weight", 0.0))
    # 1 подход = одна запись WorkoutItem
    workout_id = await _ensure_user_and_workout(cb.from_user.id)

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

    # После сохранения оставляем те же значения (фича «повторить прошлый подход»)
    await cb.message.edit_text(
        f"✅ Сохранено: <b>{_exercise_title(ex)}</b>\n"
        f"Подход: {reps} x {weight:.1f} кг\n\n"
        "Можешь добавить ещё один подход или выбрать другое упражнение.",
        reply_markup=_set_card_kb(reps, weight),
    )
    await cb.answer("Сохранено")


@training_router.callback_query(F.data == "back:exercises", Training.log_set)
async def back_to_exercises(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    page = int(data.get("ex_page", 0))
    exercises, total = await _fetch_exercises(group_id, page=page)
    await cb.message.edit_text(
        "Выбери упражнение:",
        reply_markup=_exercise_buttons(exercises, page=page, total=total, group_id=group_id),
    )
    await state.set_state(Training.choose_exercise)
    await cb.answer()


@training_router.callback_query(F.data == "finish")
async def finish_training(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    # Итог по сегодняшнему воркауту
    workout_id = await _ensure_user_and_workout(cb.from_user.id)
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(WorkoutItem).where(WorkoutItem.workout_id == workout_id))
        items = res.all()

    if not items:
        await cb.message.edit_text("Тренировка завершена. Сегодня подходов не сохранено. Ну хоть пришёл.")
        await cb.answer()
        return

    # мини-итог: тоннаж и кол-во подходов
    total_sets = len(items)
    total_tonnage = 0.0
    for it in items:
        if it.reps and it.weight:
            total_tonnage += it.reps * it.weight

    text = (
        "🏁 Тренировка завершена.\n"
        f"Подходов: <b>{total_sets}</b>\n"
        f"Тоннаж (повторы×вес): <b>{total_tonnage:.1f} кг</b>\n"
        "Сохранил. Возвращайся в меню и не исчезай на неделю."
    )
    await cb.message.edit_text(text)
    await cb.answer()
