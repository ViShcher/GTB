from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlmodel import select, func

from config import settings
from db import get_session, Workout, WorkoutItem, Exercise

reports_router = Router()

# ------------ helpers ------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _since_for(period: str) -> Optional[datetime]:
    now = _now_utc()
    if period == "weekly":
        return now - timedelta(days=7)
    if period == "monthly":
        return now - timedelta(days=30)
    if period == "alltime":
        return None
    # дефолт — неделя
    return now - timedelta(days=7)

def _fmt_int(n: Optional[int]) -> str:
    return f"{int(n or 0)}"

def _fmt_kg(n: Optional[float]) -> str:
    n = float(n or 0)
    return f"{n:,.0f} кг".replace(",", " ")

def _fmt_min(n_min: Optional[float]) -> str:
    n = float(n_min or 0)
    return f"{n:.0f} мин"

def _fmt_km(n_km: Optional[float]) -> str:
    n = float(n_km or 0)
    return f"{n:.1f} км"

def _title_for(period: str) -> str:
    return {
        "weekly": "Итоги за 7 дней",
        "monthly": "Итоги за 30 дней",
        "alltime": "Итоги за весь период",
    }.get(period, "Итоги")

async def _last_workout_summary(session, user_tg_id: int, since: Optional[datetime]) -> Tuple[Optional[Workout], bool, int, float, int, float]:
    """
    Возвращает:
      workout | None,
      in_period: bool,
      sets_count,
      tonnage_kg,
      cardio_min,
      cardio_km
    """
    # Последняя тренировка в выбранном окне
    q = (
        select(Workout)
        .where(Workout.user_id.in_(
            select(Workout.user_id).where(Workout.user_id == user_tg_id)
        ))
    )
    # user_id в нашей модели — это внутренний id. Тут проще сделать джоин через items.
    # Ищем последнюю тренировку по items.
    base = select(Workout).join(WorkoutItem, WorkoutItem.workout_id == Workout.id)
    if since is not None:
        base = base.where(WorkoutItem.created_at >= since)
    base = base.order_by(Workout.created_at.desc()).limit(1)
    res = await session.exec(base)
    wk = res.first()
    in_period = True

    if wk is None:
        # нет в окне — берём последнюю вообще
        base2 = (
            select(Workout)
            .join(WorkoutItem, WorkoutItem.workout_id == Workout.id)
            .order_by(Workout.created_at.desc())
            .limit(1)
        )
        res2 = await session.exec(base2)
        wk = res2.first()
        in_period = False

    if wk is None:
        return None, False, 0, 0.0, 0, 0.0

    # Считаем краткий итог по этой тренировке
    q_items = select(WorkoutItem).where(WorkoutItem.workout_id == wk.id)
    items = (await session.exec(q_items)).all()

    sets_count = len(items)
    tonnage = 0.0
    cardio_sec = 0
    cardio_m = 0.0

    # нужно знать тип упражнения
    if items:
        ex_ids = {it.exercise_id for it in items if it.exercise_id}
        ex_map = {}
        if ex_ids:
            q_ex = select(Exercise.id, Exercise.type).where(Exercise.id.in_(ex_ids))
            for eid, etype in (await session.exec(q_ex)).all():
                ex_map[eid] = etype or "strength"

        for it in items:
            etype = ex_map.get(it.exercise_id, "strength")
            if etype == "strength":
                if it.weight and it.reps:
                    tonnage += float(it.weight) * int(it.reps)
            else:
                if it.duration_sec:
                    cardio_sec += int(it.duration_sec)
                if it.distance_m:
                    cardio_m += float(it.distance_m)

    return wk, in_period, sets_count, tonnage, int(cardio_sec / 60), float(cardio_m / 1000.0)

async def _aggregate(session, user_tg_id: int, since: Optional[datetime]):
    # фильтр по окну и user: по факту user_id у нас на Workout, а считаем по items
    # считаем по всем items и джоиним Exercise/Workout для типов и владельца
    filters = []
    if since is not None:
        filters.append(WorkoutItem.created_at >= since)

    # только записи пользователя
    # через join на Workout
    # кол-во уникальных тренировок
    q_workouts = (
        select(func.count(func.distinct(WorkoutItem.workout_id)))
        .join(Workout, Workout.id == WorkoutItem.workout_id)
        .where(Workout.user_id == user_tg_id)
    )
    for f in filters:
        q_workouts = q_workouts.where(f)
    workouts_count = (await session.exec(q_workouts)).one() or 0

    # тоннаж по силовым
    q_tonnage = (
        select(func.sum(WorkoutItem.reps * WorkoutItem.weight))
        .join(Workout, Workout.id == WorkoutItem.workout_id)
        .join(Exercise, Exercise.id == WorkoutItem.exercise_id)
        .where(Workout.user_id == user_tg_id, Exercise.type == "strength", WorkoutItem.reps.is_not(None), WorkoutItem.weight.is_not(None))
    )
    for f in filters:
        q_tonnage = q_tonnage.where(f)
    tonnage = (await session.exec(q_tonnage)).one() or 0

    # кардио время/дистанция
    q_cardio = (
        select(func.sum(WorkoutItem.duration_sec), func.sum(WorkoutItem.distance_m))
        .join(Workout, Workout.id == WorkoutItem.workout_id)
        .join(Exercise, Exercise.id == WorkoutItem.exercise_id)
        .where(Workout.user_id == user_tg_id, Exercise.type == "cardio")
    )
    for f in filters:
        q_cardio = q_cardio.where(f)
    cardio_sec, cardio_m = (await session.exec(q_cardio)).one()
    cardio_min = (cardio_sec or 0) / 60.0
    cardio_km = (cardio_m or 0) / 1000.0

    # ТОП-3 силовые: по количеству подходов, затем по тоннажу
    q_top_str = (
        select(Exercise.name, func.count(WorkoutItem.id), func.sum(WorkoutItem.reps * WorkoutItem.weight))
        .join(Workout, Workout.id == WorkoutItem.workout_id)
        .join(Exercise, Exercise.id == WorkoutItem.exercise_id)
        .where(Workout.user_id == user_tg_id, Exercise.type == "strength")
        .group_by(Exercise.name)
        .order_by(func.count(WorkoutItem.id).desc(), func.sum(WorkoutItem.reps * WorkoutItem.weight).desc())
        .limit(3)
    )
    for f in filters:
        q_top_str = q_top_str.where(f)
    top_strength = (await session.exec(q_top_str)).all()

    # ТОП-3 кардио: по времени, затем по дистанции
    q_top_cardio = (
        select(Exercise.name, func.sum(WorkoutItem.duration_sec), func.sum(WorkoutItem.distance_m))
        .join(Workout, Workout.id == WorkoutItem.workout_id)
        .join(Exercise, Exercise.id == WorkoutItem.exercise_id)
        .where(Workout.user_id == user_tg_id, Exercise.type == "cardio")
        .group_by(Exercise.name)
        .order_by(func.sum(WorkoutItem.duration_sec).desc(), func.sum(WorkoutItem.distance_m).desc())
        .limit(3)
    )
    for f in filters:
        q_top_cardio = q_top_cardio.where(f)
    top_cardio = (await session.exec(q_top_cardio)).all()

    return {
        "workouts_count": int(workouts_count),
        "tonnage": float(tonnage or 0),
        "cardio_min": float(cardio_min or 0),
        "cardio_km": float(cardio_km or 0),
        "top_strength": top_strength,
        "top_cardio": top_cardio,
    }

def _render(period: str, agg, last_block: str) -> str:
    title = _title_for(period)
    txt = [
        f"<b>{title}</b> 📊",
        "",
        f"🏋️‍♂️ Тренировок: <b>{_fmt_int(agg['workouts_count'])}</b>",
        f"📦 Тоннаж: <b>{_fmt_kg(agg['tonnage'])}</b>",
        f"⏱ Кардио: <b>{_fmt_min(agg['cardio_min'])}</b>",
        f"📏 Дистанция: <b>{_fmt_km(agg['cardio_km'])}</b>",
        "",
        "🥇 <u>Силовые ТОП-3</u>",
    ]
    if agg["top_strength"]:
        for i, (name, cnt, ton) in enumerate(agg["top_strength"], 1):
            txt.append(f"{i}) {name} — {int(cnt)} подходов")
    else:
        txt.append("— нет данных")

    txt += ["", "🥇 <u>Кардио ТОП-3</u>"]
    if agg["top_cardio"]:
        for i, (name, dur, dist) in enumerate(agg["top_cardio"], 1):
            mins = int((dur or 0) / 60)
            km = float((dist or 0) / 1000.0)
            txt.append(f"{i}) {name} — {mins} мин / {km:.1f} км")
    else:
        txt.append("— нет данных")

    if last_block:
        txt += ["", last_block]

    return "\n".join(txt)

async def _handle_period(msg: Message, period: str):
    since = _since_for(period)
    user_tg_id = msg.from_user.id

    async with await get_session(settings.database_url) as session:
        agg = await _aggregate(session, user_tg_id, since)
        wk, in_period, sets_count, tonnage, cmin, ckm = await _last_workout_summary(session, user_tg_id, since)

    if wk is None and agg["workouts_count"] == 0 and agg["cardio_min"] == 0 and agg["tonnage"] == 0:
        await msg.answer("За выбранный период данных нет. Начни с `/train` или `/cardio`.")
        return

    last_block = ""
    if wk is not None:
        tag = "" if in_period else " (вне периода)"
        last_block = (
            f"📅 Последняя тренировка{tag}: {wk.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"— {sets_count} подходов, {tonnage:.0f} кг; кардио {cmin} мин / {ckm:.1f} км"
        )

    text = _render(period, agg, last_block)
    await msg.answer(text)

# ------------ handlers ------------
@reports_router.message(Command("weekly"))
async def weekly(msg: Message):
    await _handle_period(msg, "weekly")

@reports_router.message(Command("monthly"))
async def monthly(msg: Message):
    await _handle_period(msg, "monthly")

@reports_router.message(Command("alltime"))
async def alltime(msg: Message):
    await _handle_period(msg, "alltime")
