# routers/training.py — автофиниш 2ч и «якорь» списка упражнений внизу
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Iterable, List
import re

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlmodel import select
from sqlalchemy import func, case

from config import settings
from db import get_session, User, Workout, WorkoutItem, Exercise, MuscleGroup
from routers.profile import main_menu

training_router = Router()

# ========= FSM =========
class Training(StatesGroup):
    choose_group = State()
    choose_exercise = State()
    log_set = State()  # ввод подходов для выбранного упражнения

# ========= Парсер ввода =========
# Разделитель между весом и повторами: пробел, "/", "x" или "х"
# Запятая/точка допустимы ТОЛЬКО внутри веса (112,5; 24.5 и т.п.)
STRENGTH_INPUT_RE = re.compile(
    r"^\s*(?P<kg>\d+(?:[.,]\d+)?)\s*(?:/|x|х|\s+)\s*(?P<reps>\d+)\s*$",
    re.IGNORECASE,
)

# ========= Утилиты =========
async def _safe_cb_answer(cb: CallbackQuery):
    try:
        await cb.answer()
    except TelegramBadRequest:
        pass

async def _get_user(tg_id: int) -> Optional[User]:
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == tg_id))
        return res.first()

async def _create_workout_for_user(tg_id: int) -> int:
    """Создаём новую силовую тренировку и возвращаем ID."""
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
    rows.append([InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="workout:finish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _exercises_kb(exercises: list[Exercise]) -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(text=e.name, callback_data=f"ex:{e.id}") for e in exercises]
    rows = _chunk(btns, 2)
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад к группам", callback_data="back:groups"),
        InlineKeyboardButton(text="🏁 Завершить тренировку", callback_data="workout:finish"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _exercise_panel_kb(has_last: bool) -> InlineKeyboardMarkup:
    """
    До первого подхода: только «Назад к группам».
    После первого: «Ещё такой же» + «Завершить упражнение».
    """
    if not has_last:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к группам", callback_data="back:groups")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё такой же", callback_data="ex:repeat")],
            [InlineKeyboardButton(text="✅ Завершить упражнение", callback_data="ex:finish")],
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

async def _last_set_for_ex(workout_id: int, exercise_id: int) -> tuple[Optional[float], Optional[int]]:
    async with await get_session(settings.database_url) as session:
        q = (select(WorkoutItem)
             .where(WorkoutItem.workout_id == workout_id, WorkoutItem.exercise_id == exercise_id)
             .order_by(WorkoutItem.id.desc())
             .limit(1))
        item = (await session.exec(q)).first()
        if not item:
            return None, None
        return float(item.weight) if item.weight is not None else None, int(item.reps) if item.reps is not None else None

def _exercise_card_text(name: str, saved_sets: int, last_w: Optional[float], last_r: Optional[int]) -> str:
    last_str = f"{last_w:.1f} кг × {last_r}" if (last_w is not None and last_r is not None) else "—"
    return (
        f"🏋️ <b>{name}</b>\n"
        f"Подходы: <b>{saved_sets}</b> • Последний: <b>{last_str}</b>\n\n"
        f"Введи вес и повторы через \"/\" или пробел."
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

# ========= Авто-финиш тренировки (ленивый) =========
async def _check_autofinish(tg_id: int) -> Optional[int]:
    """
    Если последняя незавершённая тренировка без активности ≥ 2ч,
    закрываем её. Возвращаем workout_id, если что-то закрыли.
    """
    async with await get_session(settings.database_url) as session:
        # последняя незавершённая тренировка
        wq = (select(Workout)
              .join(User, User.id == Workout.user_id)
              .where(User.tg_id == tg_id, Workout.finished_at.is_(None))
              .order_by(Workout.created_at.desc())
              .limit(1))
        workout = (await session.exec(wq)).first()
        if not workout:
            return None

        # последняя активность: по подходам или по созданию тренировки
        iq = (select(func.max(WorkoutItem.created_at))
              .where(WorkoutItem.workout_id == workout.id))
        last_item_ts = (await session.exec(iq)).one()
        last_item_ts = last_item_ts if isinstance(last_item_ts, datetime) else None

        last_activity = max(filter(None, [workout.created_at, last_item_ts]))
        if not last_activity:
            last_activity = workout.created_at

        if datetime.utcnow() - last_activity < timedelta(hours=2):
            return None

        # закрываем
        workout.finished_at = datetime.utcnow()
        await session.add(workout)
        await session.commit()

        # опционально можем посчитать итоги и уведомить
        sets_cnt, lifted = await _workout_totals(workout.id)
        # уведомим пользователя скромно
        # вернём id — пригодится, если нужно что-то ещё
        return workout.id

# ========= Хелперы показа списков (якорь внизу) =========
async def _show_groups(msg_or_cb, state: FSMContext):
    groups = await _fetch_groups()
    text = "Выбери группу мышц:"
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(text, reply_markup=_groups_kb(groups))
    else:
        await msg_or_cb.message.edit_text(text, reply_markup=_groups_kb(groups))
    await state.set_state(Training.choose_group)

async def _show_exercises_anchored(msg_or_cb, state: FSMContext, group_id: int):
    """
    Всегда держим один актуальный список упражнений внизу.
    Создаём новое сообщение, старый список удаляем (если есть).
    """
    exs, total = await _fetch_exercises(group_id)
    text = f"Выбери упражнение ({total} найдено):"

    data = await state.get_data()
    old_id = data.get("hub_msg_id")

    if isinstance(msg_or_cb, Message):
        sent = await msg_or_cb.answer(text, reply_markup=_exercises_kb(exs))
    else:
        sent = await msg_or_cb.message.answer(text, reply_markup=_exercises_kb(exs))

    # удалим старый список, если был
    if old_id:
        try:
            chat_id = msg_or_cb.chat.id if isinstance(msg_or_cb, Message) else msg_or_cb.message.chat.id
            await (msg_or_cb.bot if isinstance(msg_or_cb, Message) else msg_or_cb.message.bot).delete_message(chat_id, old_id)
        except Exception:
            pass

    await state.update_data(hub_msg_id=sent.message_id)
    await state.set_state(Training.choose_exercise)

# ========= Старт силовой =========
@training_router.message(F.text == "🏋️ Тренировка")
async def start_training(msg: Message, state: FSMContext):
    await _check_autofinish(msg.from_user.id)

    user = await _get_user(msg.from_user.id)
    if not user:
        await msg.answer("Сначала /start и заполни профиль. Это быстро.")
        return

    workout_id = await _create_workout_for_user(msg.from_user.id)
    await state.clear()
    await state.update_data(workout_id=workout_id)

    await _show_groups(msg, state)

# ========= Выбор группы =========
@training_router.callback_query(F.data.startswith("grp:"), Training.choose_group)
async def pick_group(cb: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(cb)
    await _check_autofinish(cb.from_user.id)

    group_id = int(cb.data.split(":", 1)[1])
    await state.update_data(group_id=group_id)

    await _show_exercises_anchored(cb, state, group_id)

# ========= Назад к группам =========
@training_router.callback_query(F.data == "back:groups")
async def back_groups(cb: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(cb)
    await _check_autofinish(cb.from_user.id)
    # подчистим якорь списка упражнений, если завис
    data = await state.get_data()
    old_id = data.get("hub_msg_id")
    if old_id:
        try:
            await cb.message.bot.delete_message(cb.message.chat.id, old_id)
        except Exception:
            pass
        await state.update_data(hub_msg_id=None)
    await _show_groups(cb, state)

# ========= Выбор упражнения =========
@training_router.callback_query(F.data.startswith("ex:"), Training.choose_exercise)
async def pick_exercise(cb: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(cb)
    await _check_autofinish(cb.from_user.id)

    exercise_id = int(cb.data.split(":", 1)[1])
    await state.update_data(exercise_id=exercise_id)

    data = await state.get_data()
    workout_id = int(data.get("workout_id") or 0)

    name = await _exercise_name(exercise_id)
    saved = await _count_sets_for_ex(workout_id, exercise_id)
    last_w, last_r = await _last_set_for_ex(workout_id, exercise_id)

    await cb.message.edit_text(
        _exercise_card_text(name, saved, last_w, last_r),
        reply_markup=_exercise_panel_kb(has_last=(saved > 0)),
        parse_mode="HTML"
    )

    # запомним id сообщения экрана упражнения, чтобы обновлять счётчик и «Последний»
    await state.update_data(s_last_msg=cb.message.message_id, s_ex_name=name,
                            last_weight=last_w, last_reps=last_r)

    # Автопоказ системной клавиатуры: ForceReply с короткой подсказкой
    prompt = await cb.message.answer(
        "Введи вес и повторы через \"/\" или пробел.",
        reply_markup=ForceReply(input_field_placeholder="Вес/повторы")
    )
    await state.update_data(input_prompt_msg_id=prompt.message_id)

    await state.set_state(Training.log_set)

# ========= Завершить упражнение (только возврат к списку) =========
@training_router.callback_query(F.data == "ex:finish", Training.log_set)
async def finish_exercise(cb: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(cb)
    await _check_autofinish(cb.from_user.id)

    data = await state.get_data()
    group_id = int(data.get("group_id") or 0)

    # Чистим ForceReply-подсказку, если висит
    prompt_id = data.get("input_prompt_msg_id")
    if prompt_id:
        try:
            await cb.message.bot.delete_message(cb.message.chat.id, prompt_id)
        except Exception:
            pass
        await state.update_data(input_prompt_msg_id=None)

    if not group_id:
        await _show_groups(cb, state)
        return

    # Всегда показываем новый список внизу и удаляем старый
    await _show_exercises_anchored(cb, state, group_id)

    # Неболтливая подсказка и возврат нашего меню
    await cb.message.answer("Ещё одно упражнение?", reply_markup=main_menu())

# ========= Повторить прошлый подход кнопкой =========
@training_router.callback_query(F.data == "ex:repeat", Training.log_set)
async def repeat_last_set(cb: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(cb)
    await _check_autofinish(cb.from_user.id)

    data = await state.get_data()
    workout_id = int(data.get("workout_id") or 0)
    exercise_id = int(data.get("exercise_id") or 0)
    last_w = data.get("last_weight")
    last_r = data.get("last_reps")

    if not workout_id or not exercise_id or last_w is None or last_r is None:
        await cb.message.answer("Сначала введи первый подход вручную.")
        return

    async with await get_session(settings.database_url) as session:
        item = WorkoutItem(
            workout_id=workout_id,
            exercise_id=exercise_id,
            weight=float(last_w),
            reps=int(last_r),
            created_at=datetime.utcnow(),
        )
        session.add(item)
        await session.commit()

    # Обновляем карточку
    saved = await _count_sets_for_ex(workout_id, exercise_id)
    name = data.get("s_ex_name") or await _exercise_name(exercise_id)
    card_text = _exercise_card_text(name, saved, float(last_w), int(last_r))

    try:
        await cb.message.edit_text(card_text, reply_markup=_exercise_panel_kb(True), parse_mode="HTML")
    except Exception:
        await cb.message.answer(card_text, reply_markup=_exercise_panel_kb(True), parse_mode="HTML")

# ========= Ввод подхода =========
@training_router.message(Training.log_set, F.text)
async def log_set(msg: Message, state: FSMContext):
    await _check_autofinish(msg.from_user.id)

    raw = (msg.text or "").strip()
    m = STRENGTH_INPUT_RE.match(raw)
    if not m:
        await msg.answer("Формат: <b>вес/повторы</b> или <b>вес повторы</b>", parse_mode="HTML")
        return

    weight = float(m.group("kg").replace(",", "."))
    reps = int(m.group("reps"))
    if weight <= 0 or reps <= 0:
        await msg.answer("Нужны положительные значения.", parse_mode="HTML")
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

    # Обновляем карточку: счётчик и «Последний»
    saved = await _count_sets_for_ex(workout_id, exercise_id)
    card_text = _exercise_card_text(ex_name, saved, weight, reps)
    await state.update_data(last_weight=weight, last_reps=reps)

    try:
        await msg.bot.edit_message_text(
            chat_id=msg.chat.id,
            message_id=last_msg_id or msg.message_id,
            text=card_text,
            reply_markup=_exercise_panel_kb(saved > 0),
            parse_mode="HTML",
        )
    except Exception:
        sent = await msg.answer(card_text, reply_markup=_exercise_panel_kb(saved > 0), parse_mode="HTML")
        await state.update_data(s_last_msg=sent.message_id)

# ========= Завершить ВСЮ тренировку (только вне упражнения) =========
@training_router.callback_query(F.data == "workout:finish")
async def workout_finish(cb: CallbackQuery, state: FSMContext):
    await _safe_cb_answer(cb)
    await _check_autofinish(cb.from_user.id)

    data = await state.get_data()
    cur = await state.get_state()
    if cur and cur.endswith("log_set"):
        await cb.message.answer("Сначала «✅ Завершить упражнение». Потом — «🏁 Завершить тренировку».")
        return

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
        await cb.message.edit_text("Активной тренировки не найдено. Нажми «🏋️ Тренировка».")
        await state.clear()
        return

    sets_cnt, lifted = await _workout_totals(workout_id)
    await cb.message.edit_text(
        "🏁 Тренировка завершена!\n"
        f"Подходов: <b>{sets_cnt}</b>\n"
        f"Поднятый вес: <b>{int(lifted)} кг</b>",
        parse_mode="HTML",
    )
    await state.clear()
