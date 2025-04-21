# ------------ bot.py ---------------
import os, threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ConversationHandler, CallbackQueryHandler, CallbackContext)
from flask import Flask     # для недорогого/free плана Render

TOKEN   = os.getenv('TOKEN')          # будет задан в Render
CHANNEL = '@kvartirka61'              # канал для публикаций

PHOTO, TITLE, DIST, PRICE, CONTACT, DESC, CONFIRM = range(7)

def start(update: Update, ctx: CallbackContext):
    update.message.reply_text("Пришлите фото объекта")
    return PHOTO

def got_photo(update: Update, ctx: CallbackContext):
    ctx.user_data['photo'] = update.message.photo[-1].file_id
    update.message.reply_text("Заголовок (напр.: 2‑к, 54 м², ЖБИ)")
    return TITLE

def got_title(update: Update, ctx: CallbackContext):
    ctx.user_data['title'] = update.message.text
    update.message.reply_text("Район / Метро?")
    return DIST

def got_dist(update: Update, ctx: CallbackContext):
    ctx.user_data['dist'] = update.message.text
    update.message.reply_text("Цена?")
    return PRICE

def got_price(update: Update, ctx: CallbackContext):
    ctx.user_data['price'] = update.message.text
    update.message.reply_text("Контакт (@ник или телефон)")
    return CONTACT

def got_contact(update: Update, ctx: CallbackContext):
    ctx.user_data['contact'] = update.message.text
    update.message.reply_text("Описание (или «‑» если нет)")
    return DESC

def got_desc(update: Update, ctx: CallbackContext):
    ctx.user_data['desc'] = update.message.text
    txt = (f"🏠 <b>{ctx.user_data['title']}</b>\n"
           f"📍 {ctx.user_data['dist']}\n"
           f"💰 <b>{ctx.user_data['price']} ₽</b>\n"
           f"📞 {ctx.user_data['contact']}\n\n"
           f"{ctx.user_data['desc']}")
    kb = [[InlineKeyboardButton("✅ Опубликовать", callback_data='yes'),
           InlineKeyboardButton("🔄 Изменить", callback_data='no')]]
    update.message.reply_photo(ctx.user_data['photo'], caption=txt,
                               parse_mode='HTML',
                               reply_markup=InlineKeyboardMarkup(kb))
    return CONFIRM

def confirm(update: Update, ctx: CallbackContext):
    q = update.callback_query
    q.answer()
    if q.data == 'yes':
        ctx.bot.send_photo(CHANNEL, ctx.user_data['photo'],
                           caption=q.message.caption, parse_mode='HTML')
        q.edit_message_caption("✅ Опубликовано!")
        return ConversationHandler.END
    else:
        q.edit_message_text("Начнём заново. Пришлите фото.")
        return PHOTO

def cancel(update: Update, ctx: CallbackContext):
    update.message.reply_text("Отменено.")
    return ConversationHandler.END

def main():
    application = Application.builder().token("7616498446:AAGAlSXh9F0uQq2nfBc-jI15be5chdQPSXA").build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('new', start)],
        states={
            PHOTO:  [MessageHandler(filters.PHOTO, got_photo)],
            TITLE:  [MessageHandler(filters.TEXT, got_title)],
            DIST:   [MessageHandler(filters.TEXT, got_dist)],
            PRICE:  [MessageHandler(filters.TEXT, got_price)],
            CONTACT:[MessageHandler(filters.TEXT, got_contact)],
            DESC:   [MessageHandler(filters.TEXT, got_desc)],
            CONFIRM:[CallbackQueryHandler(confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(conv)

    # мини‑HTTP‑сервер, чтобы бесплатный Render не «засыпал»
    flask_app = Flask(__name__)
    @flask_app.route('/')
    def root(): return 'ok', 200
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0',
                                                  port=int(os.getenv('PORT', 8000))),
                     daemon=True).start()

    application.run_polling()

if __name__ == '__main__':
    main()