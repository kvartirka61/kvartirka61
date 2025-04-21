# -*- coding: utf-8 -*-
"""
Flask + Telegram‑бот (polling).  PTB 20.7

ENV‑переменные
TOKEN   – токен бота          (обязательно)
CHANNEL – @username / id канала (по‑умолчанию @kvartirka61)
PORT    – порт Flask (Render передаёт автоматически)
"""

from __future__ import annotations

import logging
import os
from typing import Final, List

from flask import Flask, Response
from httpx import Limits
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      InputMediaPhoto, InputMediaVideo, Update)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ConversationHandler, ContextTypes,
                          Defaults, MessageHandler, filters)
from telegram.request import HTTPXRequest

# ──────────────────── конфигурация ──────────────────────
TOKEN:   Final[str] = os.getenv("TOKEN", "")
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")  # ← канал по‑умолчанию
PORT:    Final[int] = int(os.getenv("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("Нужна переменная окружения TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

MAX_PHOTOS: Final[int] = 9
CONCURRENT_UPDATES: Final[int] = 32

# ─────────── ConversationHandler: состояния ─────────────
(
    VIDEO, PHOTO, TYPE, DISTRICT, ADDRESS,
    ROOMS, LAND, FLOORS, AREA, PRICE, CONFIRM,
) = range(11)

# ───────────────────── helpers ──────────────────────────
def html(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

async def _is_subscribed(bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(CHANNEL, user_id)
        return m.status in {
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
        f"🔒 Для работы с ботом подпишитесь на {link}"
    )
    return False

def build_ad(data: dict) -> str:
    parts = [
        f"<b>{html(data['type'])}</b>",
        f"🏘 <b>Район:</b> {html(data['district'])}",
        f"🗺 <b>Адрес:</b> {html(data['address'])}",
        f"🚪 <b>Комнат:</b> {html(data['rooms'])}",
        f"🌳 <b>Участок:</b> {html(data['land'])}",
        f"🏢 <b>Этажей:</b> {html(data['floors'])}",
        f"📐 <b>Площадь:</b> {html(data['area'])}",
        f"💰 <b>Цена:</b> {html(data['price'])}",
        "\n📞 Писать в ЛС продавцу",
    ]
    return "\n".join(parts)

# ───────────────────── команды ──────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await require_sub(update, ctx):
        return
    await update.message.reply_text(
        "Привет!\n"
        "/new — добавить объявление\n"
        "/cancel — отменить ввод\n"
        "/help — помощь\n"
        "/ping — проверка связи"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# ─────────────── Conversation: /new ─────────────────────
async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await require_sub(update, ctx):
        return ConversationHandler.END
    ctx.user_data.clear()
    await update.message.reply_text(
        "Шаг 1/10\nПришлите ВИДЕО объекта или /skip",
        parse_mode='HTML'
    )
    return VIDEO

async def step_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["video"] = update.message.video.file_id
    ctx.user_data["photos"]: List[str] = []
    await update.message.reply_text(
        f"Шаг 2/10\nПришлите до {MAX_PHOTOS} фото "
        "(/done когда хватит, /skip — без фото)"
    )
    return PHOTO

async def skip_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["video"] = None
    ctx.user_data["photos"]: List[str] = []
    await update.message.reply_text(
        f"Шаг 2/10\nПришлите до {MAX_PHOTOS} фото "
        "(/done когда хватит, /skip — без фото)"
    )
    return PHOTO

async def step_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    photos: List[str] = ctx.user_data["photos"]
    if len(photos) >= MAX_PHOTOS:
        await update.message.reply_text(f"Уже {MAX_PHOTOS} фото, используйте /done")
        return PHOTO
    photos.append(update.message.photo[-1].file_id)
    return PHOTO

async def photo_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Шаг 3/10\nВведите <b>тип объекта</b> (квартира, дом…)",
        parse_mode='HTML'
    )
    return TYPE

async def step_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["type"] = update.message.text.strip()
    await update.message.reply_text("Шаг 4/10\nВведите район:")
    return DISTRICT

async def step_district(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["district"] = update.message.text.strip()
    await update.message.reply_text("Шаг 5/10\nВведите адрес:")
    return ADDRESS

async def step_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["address"] = update.message.text.strip()
    await update.message.reply_text("Шаг 6/10\nСколько комнат?")
    return ROOMS

async def step_rooms(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["rooms"] = update.message.text.strip()
    await update.message.reply_text("Шаг 7/10\nПлощадь участка (м²) или '-' :")
    return LAND

async def step_land(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["land"] = update.message.text.strip()
    await update.message.reply_text("Шаг 8/10\nСколько этажей?")
    return FLOORS

async def step_floors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["floors"] = update.message.text.strip()
    await update.message.reply_text("Шаг 9/10\nОбщая площадь (м²):")
    return AREA

async def step_area(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["area"] = update.message.text.strip()
    await update.message.reply_text("Шаг 10/10\nЦена:")
    return PRICE

async def step_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["price"] = update.message.text.strip()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Опубликовать", callback_data="ok"),
         InlineKeyboardButton("❌ Отмена",      callback_data="cancel")],
    ])
    await update.message.reply_text(
        "Проверьте объявление и нажмите кнопку:",
        reply_markup=kb,
        disable_web_page_preview=True
    )
    await update.message.reply_text(build_ad(ctx.user_data), parse_mode='HTML')
    return CONFIRM

async def step_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Отменено.")
        return ConversationHandler.END

    data = ctx.user_data
    text = build_ad(data)

    if data["video"]:
        await ctx.bot.send_video(CHANNEL, data["video"],
                                 caption=text, parse_mode='HTML')
    elif data["photos"]:
        media = [InputMediaPhoto(pid) for pid in data["photos"][:10]]
        media[0].caption = text
        media[0].parse_mode = 'HTML'
        await ctx.bot.send_media_group(CHANNEL, media)
    else:
        await ctx.bot.send_message(CHANNEL, text, parse_mode='HTML')

    await query.edit_message_text("✅ Опубликовано!")
    return ConversationHandler.END

async def step_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог отменён.")
    return ConversationHandler.END

# ──────────────── Application / Handlers ───────────────
request_cfg = HTTPXRequest(
    connect_timeout=15,
    read_timeout=15,
    pool_limits=Limits(max_connections=20, max_keepalive_connections=20),
    max_retries=1,
)

application = (
    ApplicationBuilder()
    .token(TOKEN)
    .defaults(Defaults(parse_mode=ParseMode.HTML))
    .concurrent_updates(CONCURRENT_UPDATES)
    .request(request_cfg)
    .build()
)

application.add_handler(CommandHandler(["start", "help"], cmd_start))
application.add_handler(CommandHandler("ping", cmd_ping))

conv = ConversationHandler(
    entry_points=[CommandHandler("new", cmd_new)],
    states={
        VIDEO:    [MessageHandler(filters.VIDEO, step_video),
                   CommandHandler("skip", skip_video)],
        PHOTO:    [MessageHandler(filters.PHOTO, step_photo),
                   CommandHandler("done", photo_done),
                   CommandHandler("skip", photo_done)],
        TYPE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, step_type)],
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
    name="publish_ad",
    persistent=False,
)
application.add_handler(conv)

# ───────────────────── Flask WSGI ───────────────────────
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET", "HEAD"])
def index() -> Response:
    return Response("OK", 200)

if __name__ == "__main__":
    application.run_polling()