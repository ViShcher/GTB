from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
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
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="🚴 Кардио")],
            [KeyboardButton(text="📈 История")],
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

# ===== Состояния редактирования профиля =====
class Edit(StatesGroup):
    goal = State()
    gender = State()
    weight = State()
    height = State()
    age = State()

# ===== Вспомогательные клавиатуры =====
def goals_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Похудение", callback_data="goal:lose_weight")],
        [InlineKeyboardButton(text="💪 Масса", callback_data="goal:gain_muscle")],
        [InlineKeyboardButton(text="🦴 Здоровье спины", callback_data="goal:health")],
        [InlineKeyboardButton(text="Не выбрано", callback_data="goal:none")],
    ])

def gender_kb() -> InlineKeyboardMarkup:
    # По задаче: только Муж / Жен
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Муж", callback_data="gender:male"),
         InlineKeyboardButton(text="Жен", callback_data="gender:female")],
    ])

def stepper_kb(prefix: str, value: float, steps: list[float], unit: str, done: bool, with_back: bool = False) -> InlineKeyboardMarkup:
    row_minus = [InlineKeyboardButton(text=f"−{s}", callback_data=f"{prefix}:dec:{s}") for s in steps if s > 0]
    row_plus = [InlineKeyboardButton(text=f"+{s}", callback_data=f"{prefix}:inc:{s}") for s in steps if s > 0]
    rows = [row_minus, row_plus]
    if done:
        rows.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"{prefix}:ok")])
    if with_back:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="confirm:yes"),
         InlineKeyboardButton(text="✏️ Изменить", callback_data="confirm:edit")],
    ])

def settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="settings:profile")],
    ])

def profile_edit_kb() -> InlineKeyboardMarkup:
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

# ===== Выбор цели (онбординг) =====
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

# ===== Пол (онбординг) =====
@profile_router.callback_query(F.data.startswith("gender:"), Onb.gender)
async def pick_gender(cb: CallbackQuery, state: FSMContext):
    gender = cb.data.split(":", 1)[1]
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
        user = res.first()
        user.gender = gender
        await session.commit()
    await state.update_data(weight=70.0)
    await cb.message.edit_text(
        f"Вес: 70.0 кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", 70.0, [0.5, 1, 2.5, 5], "кг", True),
    )
    await state.set_state(Onb.weight)
    await cb.answer()

# ===== Вес: инкременты (онбординг и редактирование) =====
@profile_router.callback_query(F.data.startswith("w:"), Onb.weight)
@profile_router.callback_query(F.data.startswith("w:"), Edit.weight)
async def weight_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    w = float(data.get("weight", 70.0))

    parts = cb.data.split(":", maxsplit=2)  # ["w","inc","2.5"] | ["w","ok"]
    action = parts[1]

    def render(val: float, with_back: bool) -> InlineKeyboardMarkup:
        return stepper_kb("w", val, [0.5, 1, 2.5, 5], "кг", True, with_back=with_back)

    # где мы: онбординг или редактирование
    cur_state = await state.get_state()
    in_edit = cur_state and cur_state.startswith(Edit.__name__)

    if action == "inc":
        step = float(parts[2])
        w = min(300.0, round(w + step, 1))
        await state.update_data(weight=w)
        await cb.message.edit_text(
            f"Вес: {w:.1f} кг\nНастрой кнопками и нажми «Готово».",
            reply_markup=render(w, with_back=in_edit),
        )
        await cb.answer()
        return

    if action == "dec":
        step = float(parts[2])
        w = max(30.0, round(w - step, 1))
        await state.update_data(weight=w)
        await cb.message.edit_text(
            f"Вес: {w:.1f} кг\nНастрой кнопками и нажми «Готово».",
            reply_markup=render(w, with_back=in_edit),
        )
        await cb.answer()
        return

    if action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
            user.weight_kg = round(w, 1)
            await session.commit()

        if in_edit:
            await cb.message.edit_text("✅ Сохранено: Вес обновлён.")
            # показать карточку профиля
            await show_profile_card(cb.message)
            await state.clear()
        else:
            await state.update_data(height=175)
            await cb.message.edit_text(
                f"Рост: 175 см\nНастрой кнопками и нажми «Готово».",
                reply_markup=stepper_kb("h", 175, [1, 2, 5], "см", True),
            )
            await state.set_state(Onb.height)
        await cb.answer()
        return

# ===== Рост (онбординг и редактирование) =====
@profile_router.callback_query(F.data.startswith("h:"), Onb.height)
@profile_router.callback_query(F.data.startswith("h:"), Edit.height)
async def height_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    h = int(data.get("height", 175))

    parts = cb.data.split(":", maxsplit=2)  # ["h","inc","2"] | ["h","ok"]
    action = parts[1]

    cur_state = await state.get_state()
    in_edit = cur_state and cur_state.startswith(Edit.__name__)

    if action == "inc":
        step = int(float(parts[2]))
        h = min(230, h + step)
        await state.update_data(height=h)
        await cb.message.edit_text(
            f"Рост: {h} см\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("h", h, [1, 2, 5], "см", True, with_back=in_edit),
        )
        await cb.answer()
        return

    if action == "dec":
        step = int(float(parts[2]))
        h = max(120, h - step)
        await state.update_data(height=h)
        await cb.message.edit_text(
            f"Рост: {h} см\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("h", h, [1, 2, 5], "см", True, with_back=in_edit),
        )
        await cb.answer()
        return

    if action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
            user.height_cm = h
            await session.commit()

        if in_edit:
            await cb.message.edit_text("✅ Сохранено: Рост обновлён.")
            await show_profile_card(cb.message)
            await state.clear()
        else:
            await state.update_data(age=25)
            await cb.message.edit_text(
                f"Возраст: 25 лет\nНастрой кнопками и нажми «Готово».",
                reply_markup=stepper_kb("a", 25, [1, 2, 5], "лет", True),
            )
            await state.set_state(Onb.age)
        await cb.answer()
        return

# ===== Возраст (онбординг и редактирование) =====
@profile_router.callback_query(F.data.startswith("a:"), Onb.age)
@profile_router.callback_query(F.data.startswith("a:"), Edit.age)
async def age_step(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    a = int(data.get("age", 25))

    parts = cb.data.split(":", maxsplit=2)  # ["a","inc","2"] | ["a","ok"]
    action = parts[1]

    cur_state = await state.get_state()
    in_edit = cur_state and cur_state.startswith(Edit.__name__)

    if action == "inc":
        step = int(float(parts[2]))
        a = min(100, a + step)
        await state.update_data(age=a)
        await cb.message.edit_text(
            f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", True, with_back=in_edit),
        )
        await cb.answer()
        return

    if action == "dec":
        step = int(float(parts[2]))
        a = max(10, a - step)
        await state.update_data(age=a)
        await cb.message.edit_text(
            f"Возраст: {a} лет\nНастрой кнопками и нажми «Готово».",
            reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", True, with_back=in_edit),
        )
        await cb.answer()
        return

    if action == "ok":
        async with await get_session(settings.database_url) as session:
            res = await session.exec(select(User).where(User.tg_id == cb.from_user.id))
            user = res.first()
            user.age = a
            await session.commit()

        if in_edit:
            await cb.message.edit_text("✅ Сохранено: Возраст обновлён.")
            await show_profile_card(cb.message)
            await state.clear()
        else:
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
            gender_map = {"male": "Муж", "female": "Жен", None: "Не указано"}
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

# ===== Подтверждение (онбординг) =====
@profile_router.callback_query(F.data == "confirm:yes", Onb.confirm)
async def confirm_yes(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отлично. Профиль сохранён. Главное меню ниже.")
    await cb.message.answer("Готов к работе. Что делаем?", reply_markup=main_menu())
    await cb.answer()

@profile_router.callback_query(F.data == "confirm:edit", Onb.confirm)
async def confirm_edit(cb: CallbackQuery, state: FSMContext):
    await state.update_data(weight=70.0)
    await cb.message.edit_text(
        f"Вес: 70.0 кг\nНастрой кнопками и нажми «Готово».",
        reply_markup=stepper_kb("w", 70.0, [0.5, 1, 2.5, 5], "кг", True),
    )
    await state.set_state(Onb.weight)
    await cb.answer()

# ===== Настройки =====
@profile_router.message(F.text == "⚙️ Настройки")
async def open_settings(msg: Message):
    await msg.answer("Настройки:", reply_markup=settings_menu_kb())

@profile_router.callback_query(F.data == "settings:menu")
async def open_settings_cb(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("Настройки:", reply_markup=settings_menu_kb())

# ===== Профиль (карточка + редактирование) =====
async def show_profile_card(where: Message | CallbackQuery):
    # where — объект сообщения; для колбэков передаем cb.message
    msg = where if isinstance(where, Message) else where  # тип-хинт упрощён
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == (getattr(where, "from_user", None) or getattr(where, "chat", None)).id))
        user = res.first()
    if not user:
        if isinstance(where, Message):
            await where.answer("Похоже, ты не прошёл онбординг. Нажми /start.")
        else:
            await where.answer("Похоже, ты не прошёл онбординг. Нажми /start.")
        return

    goal_map = {
        "lose_weight": "Похудение", "gain_muscle": "Масса",
        "health": "Здоровье", "none": "Не выбрано", None: "Не выбрано",
    }
    gender_map = {"male": "Муж", "female": "Жен", None: "Не указано"}

    text = (
        "Твой профиль:\n"
        f"Цель: {goal_map.get(user.goal)}\n"
        f"Пол: {gender_map.get(user.gender)}\n"
        f"Вес: {user.weight_kg} кг\n"
        f"Рост: {user.height_cm} см\n"
        f"Возраст: {user.age}\n\n"
        "Выбери, что изменить:"
    )
    # Для колбэков и сообщений одинаково используем answer/edit_text
    if isinstance(where, Message):
        await where.answer(text, reply_markup=profile_edit_kb())
    else:
        await where.edit_text(text, reply_markup=profile_edit_kb())

@profile_router.callback_query(F.data == "settings:profile")
async def open_profile_from_settings(cb: CallbackQuery):
    await cb.answer()
    await show_profile_card(cb.message)

# ===== Редактирование полей =====
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
    await show_profile_card(cb.message)
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
    await show_profile_card(cb.message)
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
        reply_markup=stepper_kb("w", w, [0.5, 1, 2.5, 5], "кг", True, with_back=True),
    )
    await state.set_state(Edit.weight)

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
        reply_markup=stepper_kb("h", h, [1, 2, 5], "см", True, with_back=True),
    )
    await state.set_state(Edit.height)

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
        reply_markup=stepper_kb("a", a, [1, 2, 5], "лет", True, with_back=True),
    )
    await state.set_state(Edit.age)

# ===== Профиль/настройки (пункт из главного меню, для совместимости) =====
@profile_router.message(Command("my_profile"))
@profile_router.message(F.text == "⚙️ Настройки")
async def show_profile_or_settings(msg: Message):
    # этот хэндлер дублируется open_settings, но пусть останется для /my_profile
    await open_settings(msg)
