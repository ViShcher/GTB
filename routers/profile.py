from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlmodel import select

from config import settings
from db import get_session, User

profile_router = Router()

# ===== Главное меню (ReplyKeyboard) =====
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="⭐ Пресеты")],
            [KeyboardButton(text="📚 Программы"), KeyboardButton(text="📈 История")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери действие",
    )

# ===== Состояния онбординга =====
class Onb(StatesGroup):
    goal = State()
    gender = State()
    weight = State()
    height = State()
    age = State()
    confirm = State()

# ===== Вспомог. клавиатуры =====
def goals_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Похудение", callback_data="goal:lose_weight")],
        [InlineKeyboardButton(text="💪 Масса", callback_data="goal:gain_muscle")],
        [InlineKeyboardButton(text="🦴 Здоровье спины", callback_data="goal:health")],
        [InlineKeyboardButton(text="Пропустить", callback_data="goal:none")],
    ])

def gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Муж", callback_data="gender:male"),
         InlineKeyboardButton(text="Жен", callback_data="gender:female")],
        [InlineKeyboardButton(text="Другое", callback_data="gender:other")],
    ])

def stepper_kb(prefix: str, value: float, steps: list[float], unit: str, done: bool) -> InlineKeyboardMarkup:
    row_minus = [InlineKeyboardButton(text=f"−{s}", callback_data=f"{prefix}:dec:{s}") for s in steps if s > 0]
    row_plus = [InlineKeyboardButton(text=f"+{s}", callback_data=f"{prefix}:inc:{s}") for s in steps if s > 0]
    rows = [row_minus, row_plus]
    if done:
        rows.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"{prefix}:ok")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="confirm:yes"),
         InlineKeyboardButton(text="✏️ Изменить", callback_data="confirm:edit")],
    ])

# ===== /start =====
@profile_router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    # ReplyKeyboardRemove не нужен: мы уже чистим меню в server.py
    # Проверяем, есть ли юзер
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == msg.from_user.id))
        user = res.first()

        if user:
            await msg.answer("Снова привет. Главное меню ниже.", reply_markup=main_menu())
            return

        # создаём пустого и начинаем онбординг
        user = User(tg_id=msg.from_user.id)
        session.add(user)
        await session.commit()

    await msg.answer("Выбери цель:", reply_markup=goals_kb())
    await state.set_state(Onb.goal)

# ===== Выбор цели =====
@profile_router.callback_query(F.data.startswith("goal:"), Onb.goal)
async def pick_goal(cb: CallbackQuery, state: FSMContext):
    goal = cb.data.split(":", 1)[1]
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
        user.goal = goal
        await session.commit()
    await cb.message.edit_text("Выбери пол:", reply_markup=gender_kb())
    await state.set_state(Onb.gender)
    await cb.answer()

# ===== Пол =====
@profile_router.callback_query(F.data.startswith("gender:"), Onb.gender)
async def pick_gender(cb: CallbackQuery, state: FSMContext):
    gender = cb.data.split(":", 1)[1]
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
        user.gender = gender
        await session.commit()
    # вес: стартовое значение 70.0
    await state.update_data(weight=70.0)
    await cb.message.edit_text(
        f"Вес: 70.0 кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", 70.0, [0.5, 1, 2.5, 5], "кг", True),
    )
    await state.set_state(Onb.weight)
    await cb.answer()

# ===== Вес: инкременты =====
@profile_router.callback_query(F.data.startswith("w:"), Onb.weight)
async def weight_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    w = float(data.get("weight", 70.0))

    parts = cb.data.split(":", maxsplit=2)  # например: ["w","inc","2.5"] или ["w","ok"]
    action = parts[1]

    if action == "inc":
        step = float(parts[2])
        w += step
        await state.update_data(weight=round(w, 1))
        await cb.message.edit_text(
            f"Вес: {round(w,1)} кг\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("w", w, [0.5, 1, 2.5, 5], "кг", True),
        )
        await cb.answer()
        return

    if action == "dec":
        step = float(parts[2])
        w = max(1.0, w - step)
        await state.update_data(weight=round(w, 1))
        await cb.message.edit_text(
            f"Вес: {round(w,1)} кг\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("w", w, [0.5, 1, 2.5, 5], "кг", True),
        )
        await cb.answer()
        return

    if action == "ok":
        # сохраняем и переходим к росту
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
            user.weight_kg = round(w, 1)
            await session.commit()

        await state.update_data(height=175)
        await cb.message.edit_text(
            f"Рост: 175 см\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("h", 175, [1, 2, 5], "см", True),
        )
        await state.set_state(Onb.height)
        await cb.answer()
        return

    await state.update_data(weight=round(w, 1))
    await cb.message.edit_text(
        f"Вес: {round(w,1)} кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", w, [0.5, 1, 2.5, 5], "кг", True),
    )
    await cb.answer()

# ===== Рост =====
@profile_router.callback_query(F.data.startswith("h:"), Onb.height)
async def height_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    h = int(data.get("height", 175))

    parts = cb.data.split(":", maxsplit=2)  # ["h","inc","2"] или ["h","ok"]
    action = parts[1]

    if action == "inc":
        step = int(float(parts[2]))
        h = min(230, h + step)
        await state.update_data(height=h)
        await cb.message.edit_text(
            f"Рост: {h} см\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("h", h, [1, 2, 5], "см", True),
        )
        await cb.answer()
        return

    if action == "dec":
        step = int(float(parts[2]))
        h = max(120, h - step)
        await state.update_data(height=h)
        await cb.message.edit_text(
            f"Рост: {h} см\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("h", h, [1, 2, 5], "см", True),
        )
        await cb.answer()
        return

    if action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
            user.height_cm = h
            await session.commit()

        await state.update_data(age=25)
        await cb.message.edit_text(
            f"Возраст: 25 лет\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("a", 25, [1, 2, 5], "лет", True),
        )
        await state.set_state(Onb.age)
        await cb.answer()
        return

# ===== Возраст =====
@profile_router.callback_query(F.data.startswith("a:"), Onb.age)
async def age_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    a = int(data.get("age", 25))

    parts = cb.data.split(":", maxsplit=2)  # ["a","inc","2"] или ["a","ok"]
    action = parts[1]

    if action == "inc":
        step = int(float(parts[2]))
        a = min(100, a + step)
        await state.update_data(age=a)
        await cb.message.edit_text(
            f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", True),
        )
        await cb.answer()
        return

    if action == "dec":
        step = int(float(parts[2]))
        a = max(10, a - step)
        await state.update_data(age=a)
        await cb.message.edit_text(
            f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", True),
        )
        await cb.answer()
        return

    if action == "ok":
        # сохраняем возраст
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
            user.age = a
            await session.commit()

        # показать сводку
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
        goal_map = {
            "lose_weight": "Похудение",
            "gain_muscle": "Масса",
            "health": "Здоровье",
            "none": "Не выбрано",
            None: "Не выбрано",
        }
        gender_map = {"male": "Муж", "female": "Жен", "other": "Другое", None: "Не указано"}
        text = (
            "Проверь данные:\n"
            f"Цель: {goal_map.get(user.goal)}\n"
            f"Пол: {gender_map.get(user.gender)}\n"
            f"Вес: {user.weight_kg} кг\n"
            f"Рост: {user.height_cm} см\n"
            f"Возраст: {user.age}\n"
        )
        await cb.message.edit_text(text, reply_markup=confirm_kb())
        await state.set_state(Onb.confirm)
        await cb.answer()
        return

    await state.update_data(age=a)
    await cb.message.edit_text(
        f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", True),
    )
    await cb.answer()

# ===== Подтверждение =====
@profile_router.callback_query(F.data == "confirm:yes", Onb.confirm)
async def confirm_yes(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отлично. Профиль сохранён. Главное меню ниже.")
    await cb.message.answer("Готов к работе. Что делаем?", reply_markup=main_menu())
    await cb.answer()

@profile_router.callback_query(F.data == "confirm:edit", Onb.confirm)
async def confirm_edit(cb: CallbackQuery, state: FSMContext):
    # Начнём правку с веса
    await state.update_data(weight=70.0)
    await cb.message.edit_text(
        f"Вес: 70.0 кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", 70.0, [0.5, 1, 2.5, 5], "кг", True),
    )
    await state.set_state(Onb.weight)
    await cb.answer()

# ===== Профиль/настройки =====
@profile_router.message(Command("my_profile"))
@profile_router.message(F.text == "⚙️ Настройки")
async def show_profile(msg: Message):
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == msg.from_user.id))
        user = res.first()

    if not user:
        await msg.answer("Похоже, ты не прошёл онбординг. Нажми /start.")
        return

    goal_map = {
        "lose_weight": "Похудение", "gain_muscle": "Масса",
        "health": "Здоровье", "none": "Не выбрано", None: "Не выбрано",
    }
    gender_map = {"male": "Муж", "female": "Жен", "other": "Другое", None: "Не указано"}

    text = (
        "Твой профиль:\n"
        f"Цель: {goal_map.get(user.goal)}\n"
        f"Пол: {gender_map.get(user.gender)}\n"
        f"Вес: {user.weight_kg} кг\n"
        f"Рост: {user.height_cm} см\n"
        f"Возраст: {user.age}\n\n"
        "Чтобы изменить — нажми /start и пройди мини-мастер ещё раз."
    )
    await msg.answer(text, reply_markup=main_menu())
