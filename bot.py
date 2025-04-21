# ---------------- bot.py ----------------
import os
import threading
import logging

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ConversationHandler, CallbackQueryHandler,
    ContextTypes,
)

# ---------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ---------------------------------------------------------------------------
TOKEN   = os.getenv("TOKEN")                          # обязателен
CHANNEL = os.getenv("CHANNEL", "@kvartirka61")        # id/юзернейм канала
PORT    = int(os.getenv("PORT", 10000))               # Render передает свой

if not TOKEN:
    raise RuntimeError("Переменная окружения TOKEN не задана!")

# ---------------------------------------------------------------------------
# СОСТОЯНИЯ ConversationHandler (/new)
# ---------------------------------------------------------------------------
PHOTO, TITLE, DIST, PRICE, CONTACT, DESC, CONFIRM = range(7)

# ---------------------------------------------------------------------------
# СЛУЖЕБНЫЕ КОМАНДЫ
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте!\n"
        "• /new – добавить объявление\n"
        "• /cancel – отменить ввод\n"
        "• /help – справка"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# ---------------------------------------------------------------------------
# ШАГИ СЦЕНАРИЯ /new
# ---------------------------------------------------------------------------
async def entry_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пришлите фото объекта")
    return PHOTO

async def step_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["photo"] = update.message.photo[-1].file_id
    await update.message.reply_text("Заголовок (например: 2‑к, 54 м², Панель)")
    return TITLE

async def step_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["title"] = update.message.text
    await update.message.reply_text("Район?")
    return DIST

async def step_dist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["dist"] = update.message.text
    await update.message.reply_text("Цена?")
    return PRICE

async def step_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["price"] = update.message.text
    await update.message.reply_text("Контакт (@ник или телефон)")
    return CONTACT

async def step_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["contact"] = update.message.text
    await update.message.reply_text("Описание (или «‑» если нет)")
    return DESC

async def step_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["desc"] = update.message.text

    caption = (
        f"🏠 <b>{ctx.user_data['title']}</b>\n"
        f"📍 {ctx.user_data['dist']}\n"
        f"💰 <b>{ctx.user_data['price']} ₽</b>\n"
        f"📞 {ctx.user_data['contact']}\n\n"
        f"{ctx.user_data['desc']}"
    )

    kb = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data="yes"),
            InlineKeyboardButton("🔄 Изменить",     callback_data="no"),
        ]
    ]

    await update.message.reply_photo(
        ctx.user_data["photo"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return CONFIRM

async def step_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        # публикуем в канал
        await ctx.bot.send_photo(
            chat_id=CHANNEL,
            photo=ctx.user_data["photo"],
            caption=query.message.caption,
            parse_mode="HTML",
        )
        await query.edit_message_caption("✅ Опубликовано!")
        return ConversationHandler.END

    # иначе начинаем заново
    await query.edit_message_text("Начнём заново. Пришлите фото.")
    return PHOTO

async def step_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# СОЗДАНИЕ Application и РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ---------------------------------------------------------------------------
application = Application.builder().token(TOKEN).build()

# обычные команды
application.add_handler(CommandHandler(["start", "help"], cmd_start))
application.add_handler(CommandHandler("ping", cmd_ping))

# conversation /new
conv = ConversationHandler(
    entry_points=[CommandHandler("new", entry_new)],
    states={
        PHOTO:   [MessageHandler(filters.PHOTO, step_photo)],
        TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_title)],
        DIST:    [MessageHandler(filters.TEXT & ~filters.COMMAND, step_dist)],
        PRICE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_price)],
        CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_contact)],
        DESC:    [MessageHandler(filters.TEXT & ~filters.COMMAND, step_desc)],
        CONFIRM: [CallbackQueryHandler(step_confirm)],
    },
    fallbacks=[CommandHandler("cancel", step_cancel)],
    per_user=True,
    per_chat=False,          # чтобы несколько пользователей могли одновременно проходить сценарий
)
application.add_handler(conv)

# ---------------------------------------------------------------------------
# Flask-приложение для health‑check
# ---------------------------------------------------------------------------
app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def index():
    return "ok", 200

# ---------------------------------------------------------------------------
# ЗАПУСК POLLING В ОТДЕЛЬНОМ ПОТОКЕ
# ---------------------------------------------------------------------------
def run_bot():
    logger.info("Starting Telegram polling…")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

def activate_bot():
    threading.Thread(target=run_bot, daemon=True).start()

# Flask 3: before_serving, Flask 2: before_first_request
if hasattr(app, "before_serving"):
    app.before_serving(activate_bot)
else:
    app.before_first_request(activate_bot)

# ---------------------------------------------------------------------------
# ЛОКАЛЬНЫЙ ЗАПУСК (python bot.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_bot()  # сначала Telegram
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)