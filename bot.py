# ---------- bot.py ----------
import os, threading
from flask import Flask
from telegram import (Update, InlineKeyboardButton,
                      InlineKeyboardMarkup)
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          filters, ConversationHandler, CallbackQueryHandler,
                          ContextTypes)

# --- переменные окружения ---
TOKEN   = os.getenv("TOKEN")                     # обязателен
CHANNEL = os.getenv("CHANNEL", "@kvartirka61_bot")   # id канала или юзернейм
PORT    = int(os.getenv("PORT", 10000))          # Render передаст свой

if not TOKEN:
    raise RuntimeError("Нет TOKEN в переменных окружения!")

# --- состояния сценария /new ---
PHOTO, TITLE, DIST, PRICE, CONTACT, DESC, CONFIRM = range(7)

# ---------- служебные команды ----------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте!\n"
        "• /new – добавить объявление\n"
        "• /cancel – отменить ввод\n"
        "• /help – помощь"
    )

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# ---------- сценарий «добавить объявление» ----------
async def step_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Заголовок (напр.: 2‑к, 54 м², Панель)")
    return TITLE

async def step_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['title'] = update.message.text
    await update.message.reply_text("Район ?")
    return DIST

async def step_dist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['dist'] = update.message.text
    await update.message.reply_text("Цена?")
    return PRICE

async def step_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['price'] = update.message.text
    await update.message.reply_text("Контакт (@ник или телефон)")
    return CONTACT

async def step_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['contact'] = update.message.text
    await update.message.reply_text("Описание (или «‑» если нет)")
    return DESC

async def step_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['desc'] = update.message.text
    caption = (
        f"🏠 <b>{ctx.user_data['title']}</b>\n"
        f"📍 {ctx.user_data['dist']}\n"
        f"💰 <b>{ctx.user_data['price']} ₽</b>\n"
        f"📞 {ctx.user_data['contact']}\n\n"
        f"{ctx.user_data['desc']}"
    )
    kb = [[InlineKeyboardButton("✅ Опубликовать", callback_data="yes"),
           InlineKeyboardButton("🔄 Изменить",     callback_data="no")]]
    await update.message.reply_photo(
        ctx.user_data['photo'],
        caption=caption,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return CONFIRM

async def step_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "yes":
        # публикуем в канал
        await ctx.bot.send_photo(
            chat_id=CHANNEL,
            photo=ctx.user_data['photo'],
            caption=q.message.caption,
            parse_mode='HTML'
        )
        await q.edit_message_caption("✅ Опубликовано!")
        return ConversationHandler.END
    else:
        await q.edit_message_text("Начнём заново. Пришлите фото.")
        return PHOTO

async def step_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ---------- создаём Application ----------
application = Application.builder().token(TOKEN).build()

# базовые команды
application.add_handler(CommandHandler(["start", "help"], cmd_start))
application.add_handler(CommandHandler("ping", cmd_ping))

# conversation /new
conv = ConversationHandler(
    entry_points=[CommandHandler("new", lambda u, c: u.message.reply_text("Пришлите фото объекта") or PHOTO)],
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
    per_chat=False, per_user=True
)
application.add_handler(conv)

# ---------- Flask‑приложение для Render ----------
app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def index():
    return "ok", 200

# ---------- запуск polling ----------
def run_bot():
    application.run_polling(close_loop=False)

# запускаем polling при первом HTTP‑запросе (gunicorn‑воркер)
@app.before_first_request
def activate_bot():
    threading.Thread(target=run_bot, daemon=True).start()

# локальный запуск: python bot.py
if __name__ == "__main__":
    run_bot()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)