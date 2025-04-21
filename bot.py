from __future__ import annotations

import asyncio
import logging
import os
import warnings
from typing import Final

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PTBUserWarning,
    filters,
)

###############################################################################
# Константы и глобальные объекты
###############################################################################

# токен и id канала/чата берём из переменных окружения
TOKEN:   Final[str] = os.environ["BOT_TOKEN"]
CHANNEL: Final[str | int] = int(os.getenv("CHANNEL_ID", "-1001234567890"))

# Conversation‑состояния
(
    STEP_TITLE,
    STEP_TEXT,
    STEP_CONFIRM,
) = range(3)

###############################################################################
# Подписка на канал
###############################################################################

# в PTB 20 статус CREATOR переименовали в OWNER; берём то, что найдётся
SUB_OWNER = getattr(ChatMemberStatus, "OWNER",
                    getattr(ChatMemberStatus, "CREATOR", None))

ALLOWED_STATUSES: set = {
    st
    for st in (
        SUB_OWNER,
        getattr(ChatMemberStatus, "CREATOR", None),
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    )
    if st is not None
}

async def _is_subscribed(bot, user_id: int) -> bool:
    try:
        status = (await bot.get_chat_member(CHANNEL, user_id)).status
    except Exception:
        return False
    return status in ALLOWED_STATUSES

async def _require_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяем подписку; если нет — просим подписаться и возвращаем False."""
    user_id = update.effective_user.id
    if await _is_subscribed(context.bot, user_id):
        return True

    link_btn = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("➕ Подписаться", url=f"https://t.me/{CHANNEL.lstrip('@')}")
    )
    await update.effective_message.reply_text(
        "Для использования бота подпишитесь на наш канал и нажмите /start",
        reply_markup=link_btn,
    )
    return False

###############################################################################
# Хендлеры команд /start, /new, /cancel
###############################################################################

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_sub(update, context):
        return
    await update.message.reply_text(
        "Здравствуйте! Отправьте /new, чтобы добавить объявление.", quote=True
    )

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_sub(update, context):
        return ConversationHandler.END
    await update.message.reply_text("Введите заголовок объявления:")
    return STEP_TITLE

async def step_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("Теперь введите текст объявления:")
    return STEP_TEXT

async def step_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["text"] = update.message.text.strip()

    text_preview = (
        f"<b>⏩ Предпросмотр</b>\n\n"
        f"<b>{context.user_data['title']}</b>\n"
        f"{context.user_data['text']}\n\n"
        "Опубликовать?"
    )
    await update.message.reply_html(
        text_preview,
        reply_markup=InlineKeyboardMarkup.inline_keyboard(
            [
                [
                    InlineKeyboardButton("✅ Да", callback_data="pub_yes"),
                    InlineKeyboardButton("❌ Нет", callback_data="pub_no"),
                ]
            ]
        ),
    )
    return STEP_CONFIRM

async def step_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "pub_yes":
        await context.bot.send_message(
            chat_id=CHANNEL,
            text=f"<b>{context.user_data['title']}</b>\n{context.user_data['text']}",
            parse_mode="HTML",
        )
        await query.edit_message_text("✅ Объявление опубликовано!")
    else:
        await query.edit_message_text("❌ Отменено.")

    context.user_data.clear()
    return ConversationHandler.END

async def step_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Диалог отменён.")
    context.user_data.clear()
    return ConversationHandler.END

###############################################################################
# Обработчик ошибок, чтобы исключения не роняли приложение
###############################################################################

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.getLogger(__name__).exception("Unhandled exception", exc_info=context.error)

###############################################################################
# Создание Application и регистрация хендлеров
###############################################################################

# отключаем предупреждение per_message
warnings.filterwarnings("ignore", category=PTBUserWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
)

application: Application = Application.builder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("new", cmd_new)],
    states={
        STEP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_title)],
        STEP_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_text)],
        STEP_CONFIRM: [CallbackQueryHandler(step_confirm, pattern="^pub_")],
    },
    fallbacks=[CommandHandler("cancel", step_cancel)],
    per_message=False,            # объявляем явно, чтобы не было warning
)

application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(conv)
application.add_error_handler(on_error)

###############################################################################
# Точка входа для локального запуска (python bot.py)
###############################################################################

if __name__ == "__main__":
    # Для запуска из gunicorn используется application.run_polling()
    # внутри gunicorn_conf.py.  Но при локальном запуске тоже поддержим:
    asyncio.run(application.initialize())
    application.run_polling(stop_signals=None)