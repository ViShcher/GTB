# routers/profile.py — финальная версия с рабочими настройками и редактированием профиля

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlmodel import select

from config import settings
from db import get_session, User

profile_router = Router()


# ===== Главное меню =====
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="🚴 Кардио")],
            [KeyboardButton(text="📈 История")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


# ===== Состояния =====
class Onb(StatesGroup):
    goal = State()
    gender = State()
    weight = State()
    height = State()
    age = State()
    confirm = State()


class Edit(StatesGroup):
    goal = State()
    gender = State()
    weight = State()
    height = State()
    age = State()


# ===== Клавиатуры =====
def goals_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Похудение", callback_data="goal:lose_weight")],
        [InlineKeyboardButton(text="💪 Масса", callback_data="goal:gain_muscle")],
        [InlineKeyboardButton(text="🦴 Здоровье спины", callback_data="goal:health")],
        [InlineKeyboardButton(text="Не выбрано", callback_data="goal:none")],
    ])


def gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Муж", callback_data="gender:male"),
         InlineKeyboardButton(text="Жен", callback_data="gender:female")],
    ])


def stepper_kb(prefix: str, value: float, steps: list[float], unit: str, with_back: bool = False):
    row_minus = [InlineKeyboardButton(text=f"−{s}", callback_data=f"{prefix}:dec:{s}") for s in steps]
    row_plus = [InlineKeyboardButton(text=f"+{s}", callback_data=f"{prefix}:inc:{s}") for s in steps]
    rows = [row_minus, row_plus, [InlineKeyboardButton(text="✅ Готово", callback_data=f"{prefix}:ok")]]
    if with_back:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="settings:profile"),
         InlineKeyboardButton(text="💬 Обратная связь", callback_data="settings:feedback")],
    ])


def profile_edit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Цель", callback_data="edit:goal"),
         InlineKeyboardButton(text="🚻 Пол", callback_data="edit:gender")],
        [InlineKeyboardButton(text="⚖️ Вес", callback_data="edit:weight"),
         InlineKeyboardButton(text="📏 Рост", callback_data="edit:height")],
        [InlineKeyboardButton(text="🎂 Возраст", callback_data="edit:age")],
        [InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="settings:menu")],
    ])


# ===== /start =====
@profile_router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == msg.from_user.id))
        user = res.first()
        if user:
            await msg.answer("Снова привет. Главное меню ниже.", reply_markup=main_menu())
            return
        user = User(tg_id=msg.from_user.id)
        session.add(user)
        await session.commit()
    await msg.answer("Выбери цель:", reply_markup=goals_kb())
    await state.set_state(Onb.goal)


# ===== Настройки =====
@profile_router.message(F.text == "⚙️ Настройки")
async def open_settings(msg: Message):
    await msg.answer("Настройки:", reply_markup=settings_menu_kb())


@profile_router.callback_query(F.data == "settings:menu")
async def open_settings_cb(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("Настройки:", reply_markup=settings_menu_kb())


# ===== Профиль =====
async def show_profile_card(message: Message, user_tg_id: int):
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == user_tg_id))
        user = res.first()
    if not user:
        await message.answer("Похоже, ты не прошёл онбординг. Нажми /start.")
        return

    goal_map = {"lose_weight": "Похудение", "gain_muscle": "Масса", "health": "Здоровье", "none": "Не выбрано"}
    gender_map = {"male": "Муж", "female": "Жен", None: "Не указано"}

    text = (
        f"Твой профиль:\n"
        f"Цель: {goal_map.get(user.goal)}\n"
        f"Пол: {gender_map.get(user.gender)}\n"
        f"Вес: {user.weight_kg} кг\n"
        f"Рост: {user.height_cm} см\n"
        f"Возраст: {user.age}\n\n"
        "Выбери, что изменить:"
    )
    await message.answer(text, reply_markup=profile_edit_kb())


@profile_router.callback_query(F.data == "settings:profile")
async def open_profile_from_settings(cb: CallbackQuery):
    await cb.answer()
    await show_profile_card(cb.message, cb.from_user.id)


# ===== Изменение отдельных полей =====
@profile_router.callback_query(F.data == "edit:goal")
async def edit_goal(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_text("Выбери цель:", reply_markup=goals_kb())
    await state.set_state(Edit.goal)


@profile_router.callback_query(F.data.startswith("goal:"), Edit.goal)
async def set_goal(cb: CallbackQuery, state: FSMContext):
    goal = cb.data.split(":", 1)[1]
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
        user.goal = goal
        await session.commit()
    await cb.message.edit_text("✅ Сохранено: Цель обновлена.")
    await show_profile_card(cb.message, cb.from_user.id)
    await state.clear()
    await cb.answer()


@profile_router.callback_query(F.data == "edit:gender")
async def edit_gender(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_text("Выбери пол:", reply_markup=gender_kb())
    await state.set_state(Edit.gender)


@profile_router.callback_query(F.data.startswith("gender:"), Edit.gender)
async def set_gender(cb: CallbackQuery, state: FSMContext):
    gender = cb.data.split(":", 1)[1]
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
        user.gender = gender
        await session.commit()
    await cb.message.edit_text("✅ Сохранено: Пол обновлён.")
    await show_profile_card(cb.message, cb.from_user.id)
    await state.clear()
    await cb.answer()


@profile_router.callback_query(F.data == "edit:weight")
async def edit_weight(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
    w = float(user.weight_kg or 70.0)
    await state.update_data(weight=w)
    await cb.message.edit_text(
        f"Вес: {w:.1f} кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", w, [0.5, 1, 2.5, 5], "кг", with_back=True),
    )
    await state.set_state(Edit.weight)


@profile_router.callback_query(F.data.startswith("w:"), Edit.weight)
async def weight_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    w = float(data.get("weight", 70.0))
    parts = cb.data.split(":", maxsplit=2)
    action = parts[1]
    if action == "inc":
        step = float(parts[2]); w = min(300.0, round(w + step, 1))
    elif action == "dec":
        step = float(parts[2]); w = max(30.0, round(w - step, 1))
    elif action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first(); user.weight_kg = w; await session.commit()
        await cb.message.edit_text("✅ Сохранено: Вес обновлён.")
        await show_profile_card(cb.message, cb.from_user.id)
        await state.clear(); await cb.answer(); return
    await state.update_data(weight=w)
    await cb.message.edit_text(
        f"Вес: {w:.1f} кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", w, [0.5, 1, 2.5, 5], "кг", with_back=True),
    ); await cb.answer()


@profile_router.callback_query(F.data == "edit:height")
async def edit_height(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
    h = int(user.height_cm or 175)
    await state.update_data(height=h)
    await cb.message.edit_text(
        f"Рост: {h} см\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("h", h, [1, 2, 5], "см", with_back=True),
    )
    await state.set_state(Edit.height)


@profile_router.callback_query(F.data.startswith("h:"), Edit.height)
async def height_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    h = int(data.get("height", 175))
    parts = cb.data.split(":", maxsplit=2)
    action = parts[1]
    if action == "inc":
        step = int(float(parts[2])); h = min(230, h + step)
    elif action == "dec":
        step = int(float(parts[2])); h = max(120, h - step)
    elif action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first(); user.height_cm = h; await session.commit()
        await cb.message.edit_text("✅ Сохранено: Рост обновлён.")
        await show_profile_card(cb.message, cb.from_user.id)
        await state.clear(); await cb.answer(); return
    await state.update_data(height=h)
    await cb.message.edit_text(
        f"Рост: {h} см\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("h", h, [1, 2, 5], "см", with_back=True),
    ); await cb.answer()


@profile_router.callback_query(F.data == "edit:age")
async def edit_age(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
    a = int(user.age or 25)
    await state.update_data(age=a)
    await cb.message.edit_text(
        f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", with_back=True),
    )
    await state.set_state(Edit.age)


@profile_router.callback_query(F.data.startswith("a:"), Edit.age)
async def age_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    a = int(data.get("age", 25))
    parts = cb.data.split(":", maxsplit=2)
    action = parts[1]
    if action == "inc":
        step = int(float(parts[2])); a = min(100, a + step)
    elif action == "dec":
        step = int(float(parts[2])); a = max(10, a - step)
    elif action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first(); user.age = a; await session.commit()
        await cb.message.edit_text("✅ Сохранено: Возраст обновлён.")
        await show_profile_card(cb.message, cb.from_user.id)
        await state.clear(); await cb.answer(); return
    await state.update_data(age=a)
    await cb.message.edit_text(
        f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", with_back=True),
    ); await cb.answer()
