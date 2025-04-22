import os
import logging
from typing import Final

from flask import Flask, request, Response
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)

# --- Переменные окружения ---
BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET: Final[str] = os.getenv("WEBHOOK_SECRET", "")
CHANNEL: Final[str] = os.getenv("CHANNEL", "@kvartirka61")
MAX_PHOTOS: Final[int] = 10

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# --- Flask app ---
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET", "HEAD"])
def index() -> Response:
    return Response("OK", 200)

@flask_app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook() -> Response:
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        application.create_task(application.process_update(update))
    except Exception as e:
        logger.exception("Webhook handling error")
        return Response("NOK", 400)
    return Response("OK", 200)

# --- Handler states ---
PHOTO, DESCRIPTION, PRICE, CONFIRM = range(4)

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь мне фото квартиры для объявления (до 10 штук)."
    )
    context.user_data.clear()
    context.user_data["photos"] = []
    return PHOTO

async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data.get("photos", [])
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, пришли фотографию.")
        return PHOTO

    if len(photos) >= MAX_PHOTOS:
        await update.message.reply_text(
            f"Уже {MAX_PHOTOS} фото, используйте /done, чтобы закончить."
        )
        return PHOTO

    photos.append(update.message.photo[-1].file_id)
    context.user_data["photos"] = photos
    await update.message.reply_text(
        f"Фото добавлено ({len(photos)} из {MAX_PHOTOS}). Еще фото или /done."
    )
    return PHOTO

async def done_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data.get("photos", [])
    if not photos:
        await update.message.reply_text("Вы не добавили ни одной фотографии.")
        return PHOTO
    await update.message.reply_text("Теперь опишите вашу квартиру.")
    return DESCRIPTION

async def add_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text("Укажите цену, например: 30000 руб./мес.")
    return PRICE

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["price"] = update.message.text.strip()
    txt = (
        f"<b>Новое объявление!</b>\n"
        f"<b>Цена:</b> {context.user_data['price']}\n\n"
        f"{context.user_data['description']}\n"
    )
    await update.message.reply_text(
        "Ваше объявление выглядит так (будет опубликовано после /post):"
    )
    try:
        media = [InputMediaPhoto(fid) for fid in context.user_data["photos"][:MAX_PHOTOS]]
        media[0].caption = txt
        media[0].parse_mode = 'HTML'
        # Отправочка предпросмотра (пользователю, не в канал)
        await update.message.reply_media_group(media)
    except Exception as e:
        logger.warning("Не удалось отправить предпросмотр фото: %s", e)
        await update.message.reply_text(txt, parse_mode='HTML')
    return CONFIRM

async def confirm_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Публикация в канал
    txt = (
        f"<b>Новое объявление!</b>\n"
        f"<b>Цена:</b> {context.user_data['price']}\n\n"
        f"{context.user_data['description']}\n"
        f"\n\nСвязь через: @{update.effective_user.username or update.effective_user.id}"
    )
    try:
        media = [InputMediaPhoto(fid) for fid in context.user_data["photos"][:MAX_PHOTOS]]
        media[0].caption = txt
        media[0].parse_mode = 'HTML'
        await context.bot.send_media_group(CHANNEL, media)
        await update.message.reply_text("Объявление отправлено!")
    except Exception as e:
        logger.exception("Ошибка публикации в канал")
        await update.message.reply_text("Ошибка публикации. Попробуйте позже.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена. Используйте /start снова.")
    return ConversationHandler.END

# --- Telegram application definition ---
application = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .build()
)

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        PHOTO: [
            MessageHandler(filters.PHOTO & (~filters.COMMAND), add_photo),
            CommandHandler("done", done_photo)
        ],
        DESCRIPTION: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_description)],
        PRICE: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_price)],
        CONFIRM: [CommandHandler("post", confirm_post)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True,
)

application.add_handler(conv_handler)

# --- Запуск локально (разработчику) ---
if __name__ == "__main__":
    # Для отладки через polling (НЕ через Flask)
    application.run_polling()