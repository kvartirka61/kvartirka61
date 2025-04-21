# -*- coding: utf-8 -*-
"""
Flask‑приложение + Telegram‑бот (polling) в одном файле.
Совместимо с python‑telegram‑bot 20.7 и Python ≥3.11.

  Переменные окружения
  --------------------
  TOKEN        – Bot‑token от @BotFather          (обязательно)
  CHANNEL      – @username или numeric id канала  (обязательно)
  PORT         – порт, который задаёт Render ($PORT)   [10000]
  BOT_RUNNER   – 1 | 0 : 1 → запускать polling‑бота
                            0 → НЕ запускать (если нужен только Flask)

  Особенности
  -----------
  • Flask нужен лишь как health‑endpoint; работает gunicorn‑dev‑сервер.
  • Один gunicorn‑воркер (-w 1) → один поток polling → нет 409 Conflict.
  • PTBUserWarning «per_message=False» убран параметром per_message=True.
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

# ──────────────────── базовая конфигурация ────────────────────────────
TOKEN:   Final[str] = os.getenv("TOKEN", "")
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")
PORT:    Final[int] = int(os.getenv("PORT", "10000"))
BOT_RUNNER: Final[str] = os.getenv("BOT_RUNNER", "1")   # 1 – запускать бота

MAX_PHOTOS: Final[int] = 9
CONCURRENT_UPDATES: Final[int] = 32

if not TOKEN or not CHANNEL:
    raise RuntimeError("Переменные окружения TOKEN и/или CHANNEL не заданы!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

# ─────────── ConversationHandler состояния ────────────────
(
    VIDEO, PHOTO_OPTIONAL, TYPE, DISTRICT, ADDRESS,
    ROOMS, LAND, FLOORS, AREA, PRICE, CONFIRM,
) = range(11)

# ───────────────────── вспомогательные ─────────────────────
def html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))

async def _is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in {
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.RESTRICTED,
        }
    except TelegramError:
        return False

async def require_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if await _is_subscribed(ctx.bot, update.effective_user.id):
        return True
    link = CHANNEL if CHANNEL.startswith("@") else f"https://t.me/{CHANNEL}"
    await update.effective_chat.send_message(
        f"🔒 Для использования бота подпишитесь на {link}"
    )
    return False

# ───────────────────────── команды ─────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_sub(update, ctx):
        return
    await update.message.reply_text(
        "Привет!\n"
        "  /new     – добавить объявление\n"
        "  /cancel  – отменить диалог\n"
        "  /help    – помощь\n"
        "  /ping    – тест"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")

# ─────────────── conversation /new ─────────────────────────
async def new_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_sub(update, ctx):
        return ConversationHandler.END
    await update.message.reply_text("Пришлите ВИДЕО объекта")
    return VIDEO

async def step_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    v = update.effective_message.video or update.effective_message.document
    if not v:
        await update.message.reply_text("Это не видео. Попробуйте ещё раз.")
        return VIDEO
    ctx.user_data.clear()
    ctx.user_data["video"] = v.file_id
    ctx.user_data["photos"]: List[str] = []
    await update.message.reply_text(
        "Если есть фото, пришлите до 9 шт. Когда хватит — /done"
    )
    return PHOTO_OPTIONAL

async def step_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if len(ctx.user_data["photos"]) >= MAX_PHOTOS:
        await update.message.reply_text("Лимит 9 фото.")
        return PHOTO_OPTIONAL
    ctx.user_data["photos"].append(update.message.photo[-1].file_id)
    return PHOTO_OPTIONAL

async def photo_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏢 Квартира", "Квартира"),
          InlineKeyboardButton("🏡 Дом", "Дом")]]
    )
    await update.message.reply_text("Тип объекта:", reply_markup=kb)
    return TYPE

async def step_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["type"] = q.data
    await q.edit_message_text(f"Тип: {q.data}")
    await q.message.reply_text("Район?")
    return DISTRICT

async def step_district(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["district"] = update.message.text
    await update.message.reply_text("Адрес?")
    return ADDRESS

async def step_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["address"] = update.message.text
    await update.message.reply_text("Кол-во комнат?")
    return ROOMS

async def step_rooms(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["rooms"] = update.message.text
    if ctx.user_data["type"] == "Дом":
        await update.message.reply_text("Размер участка (сот.)?")
        return LAND
    await update.message.reply_text("Этаж / этажность (3/5)?")
    return FLOORS

async def step_land(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["land"] = update.message.text
    await update.message.reply_text("Этаж / этажность (1/2)?")
    return FLOORS

async def step_floors(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["floors"] = update.message.text
    await update.message.reply_text("Площадь, м²?")
    return AREA

async def step_area(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["area"] = update.message.text
    await update.message.reply_text("Цена, ₽?")
    return PRICE

async def step_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["price"] = update.message.text
    ud = ctx.user_data
    lines = [
        f"🏠 <b>{html(ud['type'])}</b>",
        f"📍 {html(ud['district'])}",
        f"📌 {html(ud['address'])}",
        f"🛏 {html(ud['rooms'])} комн.",
    ]
    if ud["type"] == "Дом":
        lines.append(f"🌳 Участок: {html(ud.get('land', '-'))} сот.")
    lines.extend([
        f"🏢 Этаж/этажн.: {html(ud['floors'])}",
        f"📐 Площадь: {html(ud['area'])} м²",
        f"💰 <b>{html(ud['price'])} ₽</b>",
    ])
    ud["caption"] = "\n".join(lines)

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Опубликовать", "yes"),
          InlineKeyboardButton("🔄 Заново", "redo")]]
    )
    await update.message.reply_video(
        ud["video"], caption=ud["caption"], reply_markup=kb
    )
    return CONFIRM

async def step_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if q.data == "yes":
        if not await _is_subscribed(ctx.bot, q.from_user.id):
            await q.edit_message_caption("🔒 Сначала подпишитесь на канал.")
            return ConversationHandler.END
        ud = ctx.user_data
        try:
            if ud["photos"]:
                media = [InputMediaVideo(ud["video"], caption=ud["caption"])]
                media += [InputMediaPhoto(pid) for pid in ud["photos"]]
                await ctx.bot.send_media_group(CHANNEL, media)
            else:
                await ctx.bot.send_video(CHANNEL, ud["video"],
                                         caption=ud["caption"])
            await q.edit_message_caption("✅ Опубликовано!")
        except TelegramError as e:
            log.error("Ошибка отправки: %s", e)
            await q.edit_message_caption("❌ Не удалось опубликовать.")
        return ConversationHandler.END
    await q.edit_message_text("Начнём заново. Пришлите видео.")
    return VIDEO

async def step_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Диалог отменён.")
    return ConversationHandler.END

# ─────────────── error‑handler ─────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка во время обработки update: %s", context.error)
    if isinstance(update, Update) and update.effective_chat:
        await context.bot.send_message(
            update.effective_chat.id, "😔 Ошибка. Попробуйте позже."
        )

# ─────────── Telegram Application (PTB‑20.7) ──────────────
application = (
    Application.builder()
    .token(TOKEN)
    .concurrent_updates(CONCURRENT_UPDATES)
    .defaults(Defaults(parse_mode=ParseMode.HTML))
    .build()
)

application.add_error_handler(error_handler)
application.add_handler(CommandHandler(["start", "help"], cmd_start))
application.add_handler(CommandHandler("ping", cmd_ping))

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("new", new_entry)],
    states={
        VIDEO: [MessageHandler(filters.VIDEO |
                               (filters.Document.VIDEO & ~filters.COMMAND),
                               step_video)],
        PHOTO_OPTIONAL: [
            MessageHandler(filters.PHOTO, step_photo),
            CommandHandler(["done", "skip"], photo_done),
        ],
        TYPE:     [CallbackQueryHandler(step_type)],
        DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_district)],
        ADDRESS:  [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_address)],
        ROOMS:    [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_rooms)],
        LAND:     [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_land)],
        FLOORS:   [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_floors)],
        AREA:     [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_area)],
        PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  step_price)],
        CONFIRM:  [CallbackQueryHandler(step_confirm)],
    },
    fallbacks=[CommandHandler("cancel", step_cancel)],
    per_user=True,
    per_message=True,        # ← нет PTBUserWarning
)

application.add_handler(conv_handler)

# ─────────────────────── Flask ─────────────────────────────
app = Flask(__name__)

@app.get("/")
def health() -> Response:
    """Health‑чек для Render (ответ 200 «ok»)."""
    return Response("ok", 200)

# ───────────── запуск polling‑бота в отдельном треде ──────
def run_bot() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    log.info("📡 Bot polling started (thread)")
    application.run_polling(
        allowed_updates=["message", "edited_message",
                         "callback_query", "my_chat_member"],
        drop_pending_updates=True,
        stop_signals=[],        # нельзя ставить signal в дочернем потоке
        close_loop=False,
    )

if BOT_RUNNER == "1":
    threading.Thread(target=run_bot, daemon=True, name="bot").start()

# ───────────── локальный запуск (python bot.py) ───────────
if __name__ == "__main__":
    app.run("0.0.0.0", PORT, use_reloader=False)