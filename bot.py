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
    filters,
)

# ---------------------------------------------------------------------------
# корректный импорт PTBUserWarning
# ---------------------------------------------------------------------------
try:                                        # PTB >= 20.1
    from telegram.warnings import PTBUserWarning
except ImportError:                         # запасной вариант (ветка до 20.1)
    from telegram._utils.warnings import PTBUserWarning    # type: ignore

###############################################################################
# Константы
###############################################################################

TOKEN:   Final[str] = os.environ["BOT_TOKEN"]
CHANNEL: Final[str | int] = int(os.getenv("CHANNEL_ID", "-1001234567890"))

STEP_TITLE, STEP_TEXT, STEP_CONFIRM = range(3)

###############################################################################
# Проверка подписки
###############################################################################

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
    if st
}

async def _is_subscribed(bot, user_id: int) -> bool:
    try:
        status = (await bot.get_chat_member(CHANNEL, user_id)).status
    except Exception:
        return False
    return status in ALLOWED_STATUSES

async def _require_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if await _is_subscribed(context.bot, update.effective_user.id):
        return True

    btn = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("➕ Подписаться", url=f"https://t.me/{str(CHANNEL).lstrip('@')}")
    )
    await update.effective_message.reply_text(
        "Сначала подпишитесь на канал и нажмите /start", reply_markup=btn
    )
    return False

###############################################################################
# Команды и шаги диалога
###############################################################################

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_sub(update, context):
        return
    await update.message.reply_text("Добро пожаловать! Для нового объявления ─ /new")

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_sub(update, context):
        return ConversationHandler.END
    await update.message.reply_text("Введите заголовок:")
    return STEP_TITLE

async def step_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("Теперь текст объявления:")
    return STEP_TEXT

async def step_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["text"] = update.message.text.strip()
    preview = (
        f"<b>⏩ Предпросмотр</b>\n\n"
        f"<b>{context.user_data['title']}</b>\n"
        f"{context.user_data['text']}\n\nОпубликовать?"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Да", callback_data="pub_yes"),
          InlineKeyboardButton("❌ Нет", callback_data="pub_no")]]
    )
    await update.message.reply_html(preview, reply_markup=kb)
    return STEP_CONFIRM

async def step_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if q.data == "pub_yes":
        await context.bot.send_message(
            CHANNEL,
            f"<b>{context.user_data['title']}</b>\n{context.user_data['text']}",
            parse_mode="HTML",
        )
        await q.edit_message_text("✅ Опубликовано!")
    else:
        await q.edit_message_text("❌ Отменено.")
    context.user_data.clear()
    return ConversationHandler.END

async def step_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Диалог отменён.")
    context.user_data.clear()
    return ConversationHandler.END

###############################################################################
# Обработчик ошибок
###############################################################################

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.getLogger(__name__).exception("Unhandled exception", exc_info=context.error)

###############################################################################
# Инициализация Application
###############################################################################

warnings.filterwarnings("ignore", category=PTBUserWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
)

application = Application.builder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("new", cmd_new)],
    states={
        STEP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_title)],
        STEP_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_text)],
        STEP_CONFIRM: [CallbackQueryHandler(step_confirm, pattern="^pub_")],
    },
    fallbacks=[CommandHandler("cancel", step_cancel)],
    per_message=False,
)

application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(conv)
application.add_error_handler(on_error)

###############################################################################
# Локальный запуск
###############################################################################

if __name__ == "__main__":
    asyncio.run(application.initialize())
    application.run_polling(stop_signals=None)