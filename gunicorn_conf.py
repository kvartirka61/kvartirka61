"""
Gunicorn‑конфигурация:
 • WSGI‑приложение — flask_app из bot.py
 • post_fork — запускает Telegram‑бот в отдельном потоке,
   чтобы один процесс обслуживал и HTTP, и polling.
"""

import os
import threading
import logging

bind          = f"0.0.0.0:{os.getenv('PORT', 8000)}"
worker_class  = "gthread"
workers       = 1
threads       = 4
timeout       = 0          # отключаем hard‑timeout
keepalive     = 5

wsgi_app = "bot:flask_app"

def post_fork(server, worker):
    from bot import application
    log = logging.getLogger("gunicorn.post_fork")
    log.info("post_fork: запускаем Telegram‑бот (PID %s)", worker.pid)

    def _run():
        application.run_polling(poll_interval=1,
                                request_timeout=50,
                                stop_signals=None)

    threading.Thread(target=_run, daemon=True).start()