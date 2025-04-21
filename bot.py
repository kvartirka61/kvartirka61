# -*- coding: utf-8 -*-
"""
Flask + Telegram‑бот (PTB 20.7).
ENV: TOKEN (обязательно), CHANNEL (≈@kvartirka61), PORT.
"""

from __future__ import annotations
import logging, os
from typing import Final, List

from flask import Flask, Response
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      InputMediaPhoto, Update)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ConversationHandler, ContextTypes,
                          Defaults, MessageHandler, filters)
from telegram.request import HTTPXRequest

# ──────────── базовая конфигурация ────────────
TOKEN:   Final[str] = os.getenv("TOKEN", "")
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")
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

# ─────────── ConversationHandler: состояния ────────────
(VIDEO, PHOTO, TYPE, DISTRICT, ADDRESS,
 ROOMS, LAND, FLOORS, AREA, PRICE, CONFIRM) = range(11)

# ------------- вспомогательные функции -----------------
def html(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))

async def _is_subscribed(bot, uid: int) -> bool:
    from telegram.error import TelegramError
    try:
        st = (await bot.get_chat_member(CHANNEL, uid)).status
        return st in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR,
                      ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}
    except TelegramError:
        return False

async def require_sub(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if await _is_subscribed(ctx.bot, upd.effective_user.id):
        return True
    link = CHANNEL if CHANNEL.startswith("@") else f"https://t.me/{CHANNEL}"
    await upd.effective_chat.send_message(
        f"🔒 Для работы с ботом подпишитесь на {link}")
    return False

def build_ad(d: dict) -> str:
    return "\n".join([
        f"<b>{html(d['type'])}</b>",
        f"🏘 <b>Район:</b> {html(d['district'])}",
        f"🗺 <b>Адрес:</b> {html(d['address'])}",
        f"🚪 <b>Комнат:</b> {html(d['rooms'])}",
        f"🌳 <b>Участок:</b> {html(d['land'])}",
        f"🏢 <b>Этажей:</b> {html(d['floors'])}",
        f"📐 <b>Площадь:</b> {html(d['area'])}",
        f"💰 <b>Цена:</b> {html(d['price'])}",
        "\n📞 Писать в ЛС продавцу",
    ])

# ---------------- команды -----------------
async def cmd_start(u, c):  # help выводит то же
    if not await require_sub(u, c): return
    await u.message.reply_text(
        "Привет!\n"
        "/new — добавить объявление\n"
        "/cancel — отменить ввод\n"
        "/help — помощь\n"
        "/ping — проверка связи")

async def cmd_ping(u, c): await u.message.reply_text("pong")

# -------- диалог /new ---------------
async def cmd_new(u, c):
    if not await require_sub(u, c): return ConversationHandler.END
    c.user_data.clear()
    await u.message.reply_text("Шаг 1/10\nПришлите ВИДЕО или /skip")
    return VIDEO

async def step_video(u, c):
    c.user_data["video"] = u.message.video.file_id
    c.user_data["photos"]: List[str] = []
    await u.message.reply_text(
        f"Шаг 2/10\nПришлите до {MAX_PHOTOS} фото "
        "(/done когда хватит, /skip — без фото)")
    return PHOTO

async def skip_video(u, c):
    c.user_data["video"] = None
    c.user_data["photos"]: List[str] = []
    await step_video(u, c)  # текст тот же
    return PHOTO

async def step_photo(u, c):
    ph = c.user_data["photos"]
    if len(ph) >= MAX_PHOTOS:
        await u.message.reply_text(f"Уже {MAX_PHOTOS} фото, используйте /done")
        return PHOTO
    ph.append(u.message.photo[-1].file_id)
    return PHOTO

async def photo_done(u, c):
    await u.message.reply_text("Шаг 3/10\nВведите <b>тип объекта</b>",
                               parse_mode='HTML')
    return TYPE

async def step_type(u, c):
    c.user_data["type"] = u.message.text.strip()
    await u.message.reply_text("Шаг 4/10\nВведите район:")
    return DISTRICT

async def step_district(u, c):
    c.user_data["district"] = u.message.text.strip()
    await u.message.reply_text("Шаг 5/10\nВведите адрес:")
    return ADDRESS

async def step_address(u, c):
    c.user_data["address"] = u.message.text.strip()
    await u.message.reply_text("Шаг 6/10\nСколько комнат?")
    return ROOMS

async def step_rooms(u, c):
    c.user_data["rooms"] = u.message.text.strip()
    await u.message.reply_text("Шаг 7/10\nПлощадь участка (м²) или '-' :")
    return LAND

async def step_land(u, c):
    c.user_data["land"] = u.message.text.strip()
    await u.message.reply_text("Шаг 8/10\nСколько этажей?")
    return FLOORS

async def step_floors(u, c):
    c.user_data["floors"] = u.message.text.strip()
    await u.message.reply_text("Шаг 9/10\nОбщая площадь (м²):")
    return AREA

async def step_area(u, c):
    c.user_data["area"] = u.message.text.strip()
    await u.message.reply_text("Шаг 10/10\nЦена:")
    return PRICE

async def step_price(u, c):
    c.user_data["price"] = u.message.text.strip()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Опубликовать", callback_data="ok"),
        InlineKeyboardButton("❌ Отмена",      callback_data="cancel")]])
    await u.message.reply_text("Проверьте объявление и нажмите кнопку:",
                               reply_markup=kb,
                               disable_web_page_preview=True)
    await u.message.reply_text(build_ad(c.user_data))
    return CONFIRM

async def step_confirm(u, c):
    q = u.callback_query
    await q.answer()
    if q.data == "cancel":
        await q.edit_message_text("❌ Отменено."); return ConversationHandler.END
    d, txt = c.user_data, build_ad(c.user_data)
    if d["video"]:
        await c.bot.send_video(CHANNEL, d["video"], caption=txt, parse_mode='HTML')
    elif d["photos"]:
        from telegram import InputMediaPhoto
        media = [InputMediaPhoto(p) for p in d["photos"][:10]]
        media[0].caption, media[0].parse_mode = txt, 'HTML'
        await c.bot.send_media_group(CHANNEL, media)
    else:
        await c.bot.send_message(CHANNEL, txt, parse_mode='HTML')
    await q.edit_message_text("✅ Опубликовано!")
    return ConversationHandler.END

async def step_cancel(u, c):
    await u.message.reply_text("Диалог отменён.")
    return ConversationHandler.END

# ─────────── HTTPXRequest – только поддерживаемые арг‑ты ──────────
def make_request_cfg() -> HTTPXRequest:
    return HTTPXRequest(connect_timeout=15, read_timeout=15)

request_cfg = make_request_cfg()

# ─────────── Application / handlers ───────────
from telegram.ext import ApplicationBuilder, CallbackQueryHandler
application = (ApplicationBuilder()
               .token(TOKEN)
               .defaults(Defaults(parse_mode=ParseMode.HTML))
               .concurrent_updates(CONCURRENT_UPDATES)
               .request(request_cfg)
               .build())

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
)
application.add_handler(conv)

# ────────── Flask health‑check ──────────
flask_app = Flask(__name__)
@flask_app.route("/", methods=["GET", "HEAD"])
def index() -> Response: return Response("OK", 200)

if __name__ == "__main__":
    application.run_polling()