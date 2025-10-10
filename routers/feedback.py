# routers/feedback.py — сбор обратной связи: подсказка остаётся, снимаем только «Отменить»,
# после отправки показываем «✅ Отправлено…» и открываем главное меню на этом же сообщении.

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlmodel import select

from config import settings
from db import get_session, User, Feedback
from routers.profile import main_menu  # используем для открытия главного меню без лишнего текста

feedback_router = Router()

# Антиспам в памяти: user_tg_id -> время последней удачной отправки
_last_sent: dict[int, datetime] = {}

class FB(StatesGroup):
    picking = State()
    typing = State()

def feedback_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐞 Проблема", callback_data="fb:type:bug"),
         InlineKeyboardButton(text="💡 Идея", callback_data="fb:type:idea")],
        [InlineKeyboardButton(text="✍️ Свободное сообщение", callback_data="fb:type:free")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:menu")],
    ])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="fb:cancel")]
    ])

# Открыть меню обратной связи (вызывается из Настроек)
@feedback_router.callback_query(F.data == "settings:feedback")
async def open_feedback_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_text("💬 Обратная связь\nВыбери тип сообщения:", reply_markup=feedback_menu_kb())
    await state.set_state(FB.picking)

# Выбор типа — показываем короткую инструкцию БЕЗ лишней строки про лимит
@feedback_router.callback_query(F.data.startswith("fb:type:"), FB.picking)
async def choose_type(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    fb_type = cb.data.split(":", 2)[2]  # bug | idea | free
    await state.update_data(fb_type=fb_type)

    prompt = {
        "bug": "✍️ Опиши проблему. По возможности укажи: что делал, что ожидал, что произошло.",
        "idea": "✍️ Опиши идею или улучшение. Чем конкретнее — тем быстрее сделаем.",
        "free": "✍️ Напиши всё, что хочешь передать разработчику.",
    }[fb_type]

    await cb.message.edit_text(prompt, reply_markup=cancel_kb())

    # запомним id этой карточки с инструкцией, чтобы после отправки убрать ТОЛЬКО кнопку
    await state.update_data(fb_prompt_msg_id=cb.message.message_id)
    await state.set_state(FB.typing)

# Отмена ввода
@feedback_router.callback_query(F.data == "fb:cancel")
async def cancel_feedback(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Отменено")
    await state.clear()
    # возвращаем меню обратной связи
    await cb.message.edit_text("💬 Обратная связь\nВыбери тип сообщения:", reply_markup=feedback_menu_kb())

# Приём текста
@feedback_router.message(FB.typing)
async def receive_text(msg: Message, state: FSMContext):
    user_tg_id = msg.from_user.id

    # Антиспам: не чаще 1 раза в 10 секунд
    now = datetime.utcnow()
    ts = _last_sent.get(user_tg_id)
    if ts and (now - ts) < timedelta(seconds=10):
        await msg.answer("Подожди немного и отправь ещё раз. Не чаще 1 раза в 10 сек.")
        return

    data = await state.get_data()
    fb_type = data.get("fb_type") or "free"
    text = (msg.text or "").strip()
    if not text:
        await msg.answer("Сообщение пустое. Напиши текст или нажми «Отменить».", reply_markup=cancel_kb())
        return

    # Сохраняем в БД
    async with await get_session(settings.database_url) as session:
        res = await session.exec(select(User).where(User.tg_id == user_tg_id))
        user: Optional[User] = res.first()

        fb = Feedback(
            user_id=user.id if user else None,
            user_tg_id=user_tg_id,
            username=msg.from_user.username,
            full_name=f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip() or None,
            type=fb_type,
            text=text,
            created_at=datetime.utcnow(),
        )
        session.add(fb)
        await session.commit()
        await session.refresh(fb)

    # Пересылаем во второго бота
    ok, err = await _relay_to_admin_bot(fb_type=fb_type,
                                        text=text,
                                        from_user=user_tg_id,
                                        username=msg.from_user.username,
                                        full_name=f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip(),
                                        feedback_id=fb.id)
    if not ok:
        await msg.answer("Не удалось отправить сообщение разработчику. Попробуй позже.")
        return

    _last_sent[user_tg_id] = now

    # 1) убираем ТОЛЬКО клавиатуру «Отменить» у старой карточки, текст оставляем прежним
    prompt_id = data.get("fb_prompt_msg_id")
    if prompt_id:
        try:
            await msg.bot.edit_message_reply_markup(
                chat_id=msg.chat.id,
                message_id=prompt_id,
                reply_markup=None
            )
        except Exception:
            pass  # не смертельно, просто не получилось снять клавиатуру

    # 2) отправляем «спасибо» и сразу открываем главное меню НА ЭТОМ ЖЕ сообщении
    thanks = "✅ Отправлено. Спасибо, мы уже притворяемся, что читаем."
    await msg.answer(thanks, reply_markup=main_menu())

    # 3) чистим состояние
    await state.clear()

async def _relay_to_admin_bot(fb_type: str, text: str, from_user: int, username: Optional[str],
                              full_name: Optional[str], feedback_id: int) -> tuple[bool, Optional[str]]:
    """
    Шлём во второго бота через sendMessage.
    settings.feedback_bot_token и settings.feedback_chat_id обязательны.
    """
    token = settings.feedback_bot_token
    chat_id = settings.feedback_chat_id
    if not token or not chat_id:
        return False, "FEEDBACK_* env not set"

    tag = {"bug": "🐞 Проблема", "idea": "💡 Идея", "free": "✍️ Сообщение"}.get(fb_type, "✍️ Сообщение")
    head = f"{tag} • #{feedback_id}"
    user_line = f"From: {full_name or ''} @{username or ''} (tg_id={from_user})".strip()

    payload = {
        "chat_id": str(chat_id),
        "text": f"{head}\n{user_line}\n\n{text}",
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(url, json=payload) as r:
                if r.status != 200:
                    return False, f"http {r.status}"
                data = await r.json()
                return bool(data.get("ok")), None
    except Exception as e:
        return False, str(e)
