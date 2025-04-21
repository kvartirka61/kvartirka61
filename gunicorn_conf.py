"""
Запуск через:  gunicorn -c gunicorn_conf.py
Роль Gunicorn – держать HTTP‑воркеры (если они есть) и параллельно
поднять Telegram‑бота, который работает в своём thread+event‑loop.
"""
import asyncio
import logging
import os
import threading

# На Render PORT будет задан автоматически. Локально можно export PORT=8000
bind          = f"0.0.0.0:{os.getenv('PORT', 8000)}"
worker_class  = "gthread"     # нужен поток, иначе бот нельзя запустить
workers       = 1
threads       = 4
timeout       = 0             # Infinite (поллинг может висеть дольше 30 c)

wsgi_app      = "bot:application"   # Flask/Django тут нет, главное – чтобы файл bot.py импортировался

def post_fork(server, worker):
    """
    Вызывается Gunicorn после форка воркера.
    Здесь стартуем polling‑бота в отдельном потоке,
    чтобы он не блокировал HTTP‑воркеров.
    """
    from bot import application

    log = logging.getLogger("gunicorn.post_fork")
    log.info("post_fork: запускаем Telegram‑бот (PID %s)", worker.pid)

    def _run_bot() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        application.run_polling(
            poll_interval=1,
            stop_signals=None,
        )

    threading.Thread(target=_run_bot, daemon=True).start()