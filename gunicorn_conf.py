"""
Gunicorn‑конфиг
 • подключает WSGI‑объект (flask_app из bot.py)
 • в post_fork запускает Telegram‑бот в отдельном потоке
"""

import os
import threading
import logging

bind          = f"0.0.0.0:{os.getenv('PORT', 8000)}"
worker_class  = "gthread"
workers       = 1
threads       = 4
timeout       = 0
keepalive     = 5

wsgi_app = "bot:flask_app"        # Flask‑приложение

def post_fork(server, worker):
    from bot import application
    log = logging.getLogger("gunicorn.post_fork")
    log.info("Стартуем Telegram‑бот (PID %s)", worker.pid)

    def _run():
        application.run_polling(
            poll_interval=1,
            request_timeout=50,
            stop_signals=None,
        )

    threading.Thread(target=_run, daemon=True).start()