# -*- coding: utf-8 -*-
"""
Flask‑приложение + Telegram‑бот (polling). PTB 20.7.
Polling **НЕ** запускается при импорте модуля — этим займётся Gunicorn
через post_fork‑хук (см. gunicorn_conf.py).

Переменные окружения
--------------------
TOKEN     – bot‑token                 (обязательно)
CHANNEL   – @username или id канала    (обязательно)
PORT      – порт для Flask [$PORT]     (10000 по умолч.)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Final, List

from flask import Flask, Response
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      InputMediaPhoto, InputMediaVideo, Update)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ConversationHandler, ContextTypes, Defaults,
                          MessageHandler, filters)

# ─────────────────── конфигурация ───────────────────────
TOKEN:   Final[str] = os.getenv("TOKEN", "")
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")
PORT:    Final[int] = int(os.getenv("PORT", "10000"))

if not TOKEN or not CHANNEL:
    raise RuntimeError("Нужны переменные окружения TOKEN и CHANNEL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

MAX_PHOTOS: Final[int] = 9
CONCURRENT_UPDATES: Final[int] = 32

# ─────────── ConversationHandler состояния ───────────────
(
    VIDEO, PHOTO_OPTIONAL, TYPE, DISTRICT, ADDRESS,
    ROOMS, LAND, FLOORS, AREA, PRICE, CONFIRM,
) = range(11)

# ───────────────────── helpers ───────────────────────────
def html(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

async def _is_subscribed(bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(CHANNEL, user_id)
        return m.status in {ChatMemberStatus.CREATOR,
                            ChatMemberStatus.ADMINISTRATOR,
                            ChatMemberStatus.MEMBER,
                            ChatMemberStatus.RESTRICTED}
    except TelegramError:
        return False

async def require_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if await _is_subscribed(ctx.bot, update.effective_user.id):
        return True
    link = CHANNEL if CHANNEL.startswith("@") else f"https://t.me/{CHANNEL}"
    await update.effective_chat.send_message(
        f"🔒 Для работы с ботом подпишитесь на {link}"
    )
    return False

# ─────────────────── команды ─────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_sub(update, ctx):
        return
    await update.message.reply_text(
        "Привет!\n"
        "/new ‑ добавить объявление\n"
        "/cancel ‑ отменить\n"
        "/help ‑ помощь\n"
        "/ping ‑ тест"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")

# ───────── Conversation /new (шаги опущены для краткости) ──────────
# --- Содержимое тех же функций, что и раньше ---
# (step_video, step_photo, photo_done, step_type, …, step_confirm, step_cancel)
#              Дословно копируем из предыдущей версии
# --------------------------------------------------------------------

# ─────────── Application (PTB 20.7) ────────────────
application = (
    Application.builder()
    .token(TOKEN)
    .defaults(Defaults(parse_mode=ParseMode.HTML))
    .concurrent_updates(CONCURRENT_UPDATES)
    .build()
)

# handlers (коротко)
application.add_handler(CommandHandler(["start", "help"], cmd_start))
application.add_handler(CommandHandler("ping", cmd_ping))

# ConversationHandler — идентичен прежнему,
# но БЕЗ per_message=True, чтобы не было warning
# conv_handler = ConversationHandler( ... )
# application.add_handler(conv_handler)
# ----> вставьте его целиком из предыдущей версии без per_message=True

# ───────── error handler ───────────────────────────
async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке update: %s", ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        await ctx.bot.send_message(update.effective_chat.id,
                                   "😔 Ошибка. Попробуйте позже.")

application.add_error_handler(error_handler)

# ─────────────────── Flask ‑ healthcheck ───────────
app = Flask(__name__)

@app.get("/")
def health() -> Response:
    return Response("ok", 200)

# ───────────────── polling‑функция ──────────────────
def run_bot() -> None:
    """Стартует polling в отдельном потоке. Вызывается из gunicorn_conf."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    log.info("📡 Bot polling started. PID=%s", os.getpid())
    application.run_polling(
        allowed_updates=["message", "edited_message",
                         "callback_query", "my_chat_member"],
        drop_pending_updates=True,
        stop_signals=[],      # нельзя ставить signal после forka
        close_loop=False,
    )

# ─────────── локальный запуск (`python bot.py`) ─────
if __name__ == "__main__":
    # 1. запускаем polling‑поток
    threading.Thread(target=run_bot, daemon=True).start()
    # 2. запускаем Flask dev‑сервер
    app.run("0.0.0.0", PORT, use_reloader=False)