import os
import requests
from flask import Flask, request

TOKEN = "7616498446:AAHLnra70Zidoq0POp5CCHq610a9JAL1SP8"
CHANNEL_ID = "@kvartirka61"  # Либо -100... если канал приватный

app = Flask(__name__)

user_states = {}
user_data = {}

QUESTIONS = [
    "Укажите район:",
    "Укажите адрес:",
    "Количество комнат:",
    "Площадь (в м²):",
    "Этаж:",
    "Этажность дома:",
    "Вид ремонта (выберите): стровариант, евроремонт, дизайнерский",
    "Комплектация мебелью и техникой:",
    "Цена (в рублях):",
    "Пожалуйста, отправьте видео объекта (или напишите 'нет', если нет видео):",
    "Пожалуйста, отправьте до 9 фото объекта. После отправки всех фото напишите 'Готово'. Если не хотите загружать фото — напишите 'нет'.",
]
FIELDS = [
    "Район",
    "Адрес",
    "Комнат",
    "Площадь",
    "Этаж",
    "Этажность",
    "Ремонт",
    "Комплектация",
    "Цена",
    "Видео",
    "Фото"
]

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "no message", 200

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # стартовое меню
    if text == "/start":
        send_main_menu(chat_id)
        user_states[chat_id] = None
        user_data[chat_id] = []
        return "ok", 200

    if text == "Загрузить объявление":
        user_states[chat_id] = 0
        user_data[chat_id] = []
        send_message(chat_id, QUESTIONS[0])
        return "ok", 200

    # FSM - логика по шагам
    if chat_id in user_states and user_states[chat_id] is not None:
        state = user_states[chat_id]

        # Шаг 9 — Видео
        if state == 9:
            if 'video' in message:
                file_id = message['video']['file_id']
                user_data[chat_id].append(file_id)
                user_states[chat_id] = state + 1
                user_data[chat_id].append([])  # для фото
                send_message(chat_id, QUESTIONS[state + 1])
            elif text.lower() == 'нет':
                user_data[chat_id].append(None)
                user_states[chat_id] = state + 1
                user_data[chat_id].append([])  # для фото
                send_message(chat_id, QUESTIONS[state + 1])
            else:
                send_message(chat_id, "Пожалуйста, отправьте видеоролик или напишите 'нет'.")
            return "ok", 200

        # Шаг 10 — Фото (до 9 фото)
        if state == 10:
            photos = user_data[chat_id][-1]
            if text.lower() == "готово":
                publish_to_channel(user_data[chat_id])
                send_message(chat_id, "Ваше объявление опубликовано в канале!")
                user_states[chat_id] = None
                user_data[chat_id] = []
                return "ok", 200
            if text.lower() == "нет" and not photos:
                user_data[chat_id][-1] = []
                publish_to_channel(user_data[chat_id])
                send_message(chat_id, "Ваше объявление опубликовано в канале!")
                user_states[chat_id] = None
                user_data[chat_id] = []
                return "ok", 200
            if 'photo' in message:
                file_id = message['photo'][-1]['file_id']
                if len(photos) < 9:
                    photos.append(file_id)
                    user_data[chat_id][-1] = photos
                    if len(photos) < 9:
                        send_message(chat_id, f"Добавлено фото {len(photos)}. Можете отправить ещё ({9 - len(photos)}). Когда закончите — напишите 'Готово'.")
                    else:
                        publish_to_channel(user_data[chat_id])
                        send_message(chat_id, "Вы загрузили 9 фото, лимит достигнут! Ваше объявление опубликовано в канале!")
                        user_states[chat_id] = None
                        user_data[chat_id] = []
                else:
                    send_message(chat_id, "Вы уже загрузили 9 фото.")
                return "ok", 200
            if 'media_group_id' in message and 'photo' in message:
                file_id = message['photo'][-1]['file_id']
                if len(photos) < 9:
                    photos.append(file_id)
                    user_data[chat_id][-1] = photos
                    if len(photos) >= 9:
                        publish_to_channel(user_data[chat_id])
                        send_message(chat_id, "Вы загрузили 9 фото, лимит достигнут! Ваше объявление опубликовано в канале!")
                        user_states[chat_id] = None
                        user_data[chat_id] = []
                return "ok", 200
            send_message(chat_id, "Пожалуйста, отправьте фото (максимум 9) или напишите 'Готово', когда закончите.")
            return "ok", 200

        # Вопросы с 0 по 8 — текстовые
        if state < 9:
            user_data[chat_id].append(text)
            user_states[chat_id] = state + 1
            send_message(chat_id, QUESTIONS[state + 1])
            return "ok", 200

    # По умолчанию выводим меню
    send_main_menu(chat_id)
    return "ok", 200

def send_message(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    requests.post(url, json=payload)

def send_main_menu(chat_id):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    keyboard = {
        "keyboard": [[{"text": "Загрузить объявление"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    payload = {
        "chat_id": chat_id,
        "text": "Добро пожаловать! Нажмите кнопку, чтобы загрузить объявление.",
        "reply_markup": keyboard
    }
    requests.post(url, json=payload)

def send_photo_album_to_channel(photo_file_ids, caption):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMediaGroup"
    media = [{"type": "photo", "media": photo_file_ids[0], "caption": caption, "parse_mode": "HTML"}]
    for pid in photo_file_ids[1:]:
        media.append({"type":"photo", "media": pid})
    payload = {
        "chat_id": CHANNEL_ID,
        "media": media
    }
    requests.post(url, json=payload)

def send_photo_to_channel(file_id, caption):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {"chat_id": CHANNEL_ID, "photo": file_id, "caption": caption, "parse_mode": 'HTML'}
    requests.post(url, json=payload)

def send_video_to_channel(file_id, caption):
    url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
    payload = {"chat_id": CHANNEL_ID, "video": file_id, "caption": caption}
    requests.post(url, json=payload)

def publish_to_channel(data):
    caption = "<b>Новое объявление:</b>\n"
    for i in range(0, 9):
        caption += f"<b>{FIELDS[i]}:</b> {data[i]}\n"
    photos = data[10]
    video = data[9]
    if photos and isinstance(photos, list) and len(photos) > 0:
        if len(photos) == 1:
            send_photo_to_channel(photos[0], caption)
        else:
            send_photo_album_to_channel(photos[:9], caption)
    else:
        send_message(CHANNEL_ID, caption, parse_mode='HTML')
    if video:
        send_video_to_channel(video, "Видео объекта")

if __name__ == "__main__":
    app.run()