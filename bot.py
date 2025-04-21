# -*- coding: utf-8 -*-
"""
Telegram‑бот для публикации объявлений в канале @kvartirka61
(PTB 20+, Flask 3).  Автор: «лучший в мире python‑программист» :)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from typing import Final, List

from flask import Flask, Response
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ----------------------------- НАСТРОЙКИ -----------------------------
TOKEN:   Final[str] = os.getenv("TOKEN", "")                 # обязательно
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")   # куда публикуем
PORT:    Final[int] = int(os.getenv("PORT", "10000"))        # Flask‑порт

MAX_PHOTOS: Final[int] = 9           # телеграм пропускает ≤10 элементов в альбоме
CONCURRENT_UPDATES: Final[int] = 32  # асинхронных апдейтов

if not TOKEN:
    print("❌  Не задан TOKEN в переменных окружения", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

# -------------------- ConversationHandler состояния -------------------
(
    VIDEO,
    PHOTO_OPTIONAL,
    TYPE,
    DISTRICT,
    ADDRESS,
    ROOMS,
    LAND,
    FLOORS,
    AREA,
    PRICE,
    CONFIRM,
) = range(11)

# --------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ------------------------
def html_escape(text: str) -> str:
    """Простейший HTML‑escape (PTB ParseMode.HTML)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

async def _is_subscribed(bot, user_id: int) -> bool:
    """
    True, если пользователь состоит в канале CHANNEL.
    Боту требуются admin‑права «can_see_members».
    """
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in (
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.RESTRICTED,  # на всякий случай
        )
    except TelegramError as e:
        log.warning("Не удалось проверить подписку (%s)", e)
        return False

async def require_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Останавливает диалог, если пользователь не подписан."""
    if await _is_subscribed(ctx.bot, update.effective_user.id):
        return True

    link = CHANNEL if CHANNEL.startswith("@") else CHANNEL
    await update.effective_chat.send_message(
        f"🔒 Доступ закрыт.\n"
        f"Подпишитесь на канал {link} и повторите команду.",
        disable_web_page_preview=True,
    )
    return False

# ----------------------------- КОМАНДЫ --------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_subscription(update, ctx):
        return
    await update.message.reply_text(
        "Привет! Я помогу разместить объявление в канале.\n"
        "• /new — добавить объявление\n"
        "• /cancel — отменить ввод\n"
        "• /help — подсказка\n"
        "• /ping — тест"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")

# -------------------- СЦЕНАРИЙ /new (Conversation) --------------------
async def new_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_subscription(update, ctx):
        return ConversationHandler.END
    await update.message.reply_text("Пришлите ВИДЕО объекта")
    return VIDEO

async def step_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    video = update.effective_message.video or update.effective_message.document
    if not video:
        await update.message.reply_text("Это не видео. Попробуйте ещё раз.")
        return VIDEO

    ctx.user_data.clear()
    ctx.user_data["video"] = video.file_id
    ctx.user_data["photos"]: List[str] = []

    await update.message.reply_text(
        "Есть фотографии? Пришлите до 9 штук подряд.\n"
        "Когда хватит — /done или /skip."
    )
    return PHOTO_OPTIONAL

async def step_photo_collect(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if len(ctx.user_data["photos"]) >= MAX_PHOTOS:
        await update.message.reply_text("Максимум 9 фотографий.")
        return PHOTO_OPTIONAL
    ctx.user_data["photos"].append(update.message.photo[-1].file_id)
    return PHOTO_OPTIONAL

async def photo_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏢 Квартира", callback_data="Квартира"),
                InlineKeyboardButton("🏡 Дом", callback_data="Дом"),
            ]
        ]
    )
    await update.message.reply_text("Вид объекта:", reply_markup=kb)
    return TYPE

async def step_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["type"] = q.data
    await q.edit_message_text(f"Вид: {q.data}")
    await q.message.reply_text("Район?")
    return DISTRICT

async def step_district(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["district"] = update.message.text
    await update.message.reply_text("Адрес?")
    return ADDRESS

async def step_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["address"] = update.message.text
    await update.message.reply_text("Количество комнат?")
    return ROOMS

async def step_rooms(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["rooms"] = update.message.text
    if ctx.user_data["type"] == "Дом":
        await update.message.reply_text("Размер участка (сот.)?")
        return LAND
    await update.message.reply_text("Этаж / этажность (например 3/5)?")
    return FLOORS

async def step_land(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["land"] = update.message.text
    await update.message.reply_text("Этаж / этажность (например 1/2)?")
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
    lines: list[str] = [
        f"🏠 <b>{html_escape(ud['type'])}</b>",
        f"📍 {html_escape(ud['district'])}",
        f"📌 {html_escape(ud['address'])}",
        f"🛏 {html_escape(ud['rooms'])} комн.",
    ]
    if ud["type"] == "Дом":
        lines.append(f"🌳 Участок: {html_escape(ud.get('land', '-'))} сот.")
    lines.extend(
        [
            f"🏢 Этаж/этажн.: {html_escape(ud['floors'])}",
            f"📐 Площадь: {html_escape(ud['area'])} м²",
            f"💰 <b>{html_escape(ud['price'])} ₽</b>",
        ]
    )
    ud["caption"] = "\n".join(lines)

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data="yes"),
                InlineKeyboardButton("🔄 Заполнить заново", callback_data="redo"),
            ]
        ]
    )
    await update.message.reply_video(
        ud["video"], caption=ud["caption"], reply_markup=kb
    )
    return CONFIRM

async def step_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    if q.data == "yes":
        # окончательная проверка подписки
        if not await _is_subscribed(ctx.bot, q.from_user.id):
            await q.edit_message_caption("🔒 Сначала подпишитесь на канал.")
            return ConversationHandler.END

        ud = ctx.user_data
        try:
            if ud["photos"]:
                media = [InputMediaVideo(ud["video"], caption=ud["caption"])]
                media += [InputMediaPhoto(pid) for pid in ud["photos"]]
                await ctx.bot.send_media_group(chat_id=CHANNEL, media=media)
            else:
                await ctx.bot.send_video(
                    chat_id=CHANNEL, video=ud["video"], caption=ud["caption"]
                )
            await q.edit_message_caption("✅ Опубликовано!")
        except TelegramError as e:
            log.error("Ошибка отправки: %s", e)
            await q.edit_message_caption("❌ Не удалось опубликовать.")
        return ConversationHandler.END

    # «redo»
    await q.edit_message_text("Заполняем заново. Пришлите видео.")
    return VIDEO

async def step_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Диалог прерван.")
    return ConversationHandler.END

# ------------------------ ОБЩИЙ ОБРАБОТЧИК ОШИБОК ---------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке апдейта: %s", context.error)
    if isinstance(update, Update) and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="😔 Что‑то сломалось, попробуйте ещё раз позже.",
        )

# ------------------ СОЗДАЁМ Telegram‑Application ----------------------
application = (
    Application.builder()
    .token(TOKEN)
    .defaults(dict(parse_mode=ParseMode.HTML))
    .concurrent_updates(CONCURRENT_UPDATES)
    .build()
)

application.add_error_handler(error_handler)
application.add_handler(CommandHandler(["start", "help"], cmd_start))
application.add_handler(CommandHandler("ping", cmd_ping))

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("new", new_entry)],
    states={
        VIDEO: [
            MessageHandler(
                filters.VIDEO | (filters.Document.VIDEO & ~filters.COMMAND),
                step_video,
            )
        ],
        PHOTO_OPTIONAL: [
            MessageHandler(filters.PHOTO, step_photo_collect),
            CommandHandler(["done", "skip"], photo_done),
        ],
        TYPE:     [CallbackQueryHandler(step_type)],
        DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_district)],
        ADDRESS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, step_address)],
        ROOMS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, step_rooms)],
        LAND:     [MessageHandler(filters.TEXT & ~filters.COMMAND, step_land)],
        FLOORS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_floors)],
        AREA:     [MessageHandler(filters.TEXT & ~filters.COMMAND, step_area)],
        PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, step_price)],
        CONFIRM:  [CallbackQueryHandler(step_confirm)],
    },
    fallbacks=[CommandHandler("cancel", step_cancel)],
    per_user=True,
)

application.add_handler(conv_handler)

# ---------------------------- Flask‑часть -----------------------------
app = Flask(__name__)

@app.get("/")
def health() -> Response:              # Render health‑check
    return Response("ok", 200)

def run_bot() -> None:
    """Запускает PTB‑пуллинг (блокирующий)."""
    log.info("📡  Bot polling started")
    application.run_polling(
        allowed_updates=[
            "message",
            "edited_message",
            "callback_query",
            "my_chat_member",
        ],
        close_loop=False,
        drop_pending_updates=True,
    )

@app.before_serving
def activate_bot() -> None:
    """Стартуем телеграм‑бот в отдельном демоне‑потоке."""
    threading.Thread(target=run_bot, daemon=True).start()

# --------------------- Локальный запуск (python bot.py) ---------------
def _shutdown(*_) -> None:
    log.info("⏹  Shutting down …")
    application.stop()
    sys.exit(0)

if __name__ == "__main__":
    # корректно завершаем по Ctrl+C / SIGTERM
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # прямо здесь запускаем поток‑бот и Flask‑dev‑server
    activate_bot()
    app.run("0.0.0.0", PORT, use_reloader=False)