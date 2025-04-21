# ----------------------------- bot.py ---------------------------------
from __future__ import annotations

import asyncio
import logging
import os
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

# ──────────────────────────── НАСТРОЙКИ ───────────────────────────────
MAX_PHOTOS: Final[int] = 9
CONCURRENT_UPDATES: Final[int] = 32

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log: Final = logging.getLogger("bot")

# ─────────────────────── ПЕРЕМЕННЫЕ ───────────────────────────────────
TOKEN:   Final[str] = os.getenv("TOKEN", "")
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")  # канал‑по‑умолчанию
PORT:    Final[int] = int(os.getenv("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("Переменная TOKEN не задана!")

# ─────────────── Состояния ConversationHandler ────────────────────────
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

# ─────────────────────── ВСПОМОГАТЕЛЬНЫЕ ──────────────────────────────
def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

async def is_subscribed(bot, user_id: int) -> bool:
    """
    Возвращает True, если user_id подписан на CHANNEL.
    Боту нужны права админа в канале.
    """
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in (
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
        )
    except TelegramError as e:
        log.warning("Не удалось проверить подписку: %s", e)
        return False

async def require_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if await is_subscribed(ctx.bot, user_id):
        return True

    link = CHANNEL if CHANNEL.startswith("@") else ""
    await update.effective_chat.send_message(
        f"🔒 Для публикации объявлений необходимо быть подписчиком канала "
        f"{link or 'нашего канала'}.\n"
        f"Подпишитесь и попробуйте снова командой /start."
    )
    return False

# ───────────────────────── КОМАНДЫ ────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_subscription(update, ctx):
        return

    await update.message.reply_text(
        "Привет!\n"
        "• /new — добавить объявление\n"
        "• /cancel — отменить ввод\n"
        "• /help — подсказка\n"
        "• /ping — проверить бота"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")

# ─────────────────────── СЦЕНАРИЙ /new ────────────────────────────────
async def new_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_subscription(update, ctx):
        return ConversationHandler.END

    await update.message.reply_text("Пришлите ВИДЕО объекта")
    return VIDEO

async def step_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    video = update.effective_message.video or update.effective_message.document
    if not video:
        await update.message.reply_text("Это не похоже на видео. Попробуйте ещё раз.")
        return VIDEO

    ctx.user_data.clear()
    ctx.user_data["video"] = video.file_id
    ctx.user_data["photos"]: List[str] = []

    await update.message.reply_text(
        "Если есть ФОТО, пришлите их (можно подряд, до 9 шт.).\n"
        "Когда закончите — /done или /skip."
    )
    return PHOTO_OPTIONAL

async def step_photo_collect(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if len(ctx.user_data["photos"]) >= MAX_PHOTOS:
        await update.message.reply_text("Достигнут лимит 9 фото.")
        return PHOTO_OPTIONAL

    ctx.user_data["photos"].append(update.message.photo[-1].file_id)
    return PHOTO_OPTIONAL

async def photo_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏢 Квартира", callback_data="Квартира"),
          InlineKeyboardButton("🏡 Дом",       callback_data="Дом")]]
    )
    await update.message.reply_text("Вид объекта:", reply_markup=kb)
    return TYPE

async def step_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ctx.user_data["type"] = query.data
    await query.edit_message_text(f"Вид объекта: {query.data}")
    await query.message.reply_text("Район?")
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
        await update.message.reply_text("Размер земельного участка (сот.)?")
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

    # ---------- формируем подпись ----------
    ud = ctx.user_data
    caption_lines: list[str] = [
        f"🏠 <b>{html_escape(ud['type'])}</b>",
        f"📍 {html_escape(ud['district'])}",
        f"📌 {html_escape(ud['address'])}",
        f"🛏 {html_escape(ud['rooms'])} комн.",
    ]
    if ud["type"] == "Дом":
        caption_lines.append(
            f"🌳 Участок: {html_escape(ud.get('land', '-') )} сот."
        )
    caption_lines.extend(
        [
            f"🏢 Этаж/этажн.: {html_escape(ud['floors'])}",
            f"📐 Площадь: {html_escape(ud['area'])} м²",
            f"💰 <b>{html_escape(ud['price'])} ₽</b>",
        ]
    )
    ud["caption"] = "\n".join(caption_lines)

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Опубликовать", callback_data="yes"),
          InlineKeyboardButton("🔄 Заполнить заново", callback_data="redo")]]
    )

    await update.message.reply_video(
        ud["video"],
        caption=ud["caption"],
        reply_markup=kb,
    )
    return CONFIRM

async def step_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        # ——— повторная проверка подписки перед публикацией ———
        if not await is_subscribed(ctx.bot, query.from_user.id):
            await query.edit_message_caption(
                "🔒 Сначала подпишитесь на канал и попробуйте снова."
            )
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
            await query.edit_message_caption("✅ Опубликовано!")
        except TelegramError as e:
            log.error("Ошибка отправки: %s", e)
            await query.edit_message_caption("❌ Не удалось опубликовать.")
        return ConversationHandler.END

    await query.edit_message_text("Ок, начнём заново. Пришлите видео.")
    return VIDEO

async def step_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ─────────────────── ОБРАБОТЧИК ОШИБОК ────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Exception while handling an update: %s", context.error)
    if isinstance(update, Update) and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="😔 Произошла ошибка. Попробуйте ещё раз позже.",
        )

# ────────────────── СОЗДАНИЕ Telegram‑приложения ──────────────────────
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
    per_message=True,
)
application.add_handler(conv_handler)

# ────────────────── Flask (health‑check) ───────────────────────────────
app = Flask(__name__)

@app.get("/")
def index() -> Response:  # type: ignore[valid-type]
    return Response("ok", 200)

# ──────────── Параллельный запуск polling + Flask ─────────────────────
def run_bot() -> None:
    log.info("⏳  starting polling …")
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

def activate_bot() -> None:
    threading.Thread(target=run_bot, daemon=True).start()

if hasattr(app, "before_serving"):
    app.before_serving(activate_bot)      # type: ignore[attr-defined]
else:
    app.before_first_request(activate_bot)  # type: ignore[attr-defined]

# ──────────────── Локальный запуск (python bot.py) ────────────────────
if __name__ == "__main__":
    run_bot()
    app.run("0.0.0.0", PORT, use_reloader=False)