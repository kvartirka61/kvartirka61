"""
Gunicorn‑конфигурация
  • WSGI‑приложение — flask_app из bot.py
  • post_fork — запускает Telegram‑бот в отдельном потоке
"""

import os
import threading
import logging

bind          = f"0.0.0.0:{os.getenv('PORT', 8000)}"
worker_class  = "gthread"
workers       = 1
threads       = 4
timeout       = 0          # бесконечный hard‑timeout
keepalive     = 5

wsgi_app = "bot:flask_app"

def post_fork(server, worker):
    """После форка (запуска воркера Gunicorn) стартуем polling‑бота."""
    from bot import application                      # noqa: WPS433
    log = logging.getLogger("gunicorn.post_fork")
    log.info("post_fork: запускаем Telegram‑бот (PID %s)", worker.pid)

    def _run() -> None:
        """Запустить polling в отдельном потоке.

        Для PTB ≥21 есть параметр request_timeout;
        в ветке 20.x его нет. Пробуем сначала «новый» вариант,
        а при TypeError – «старый».
        """
        try:
            application.run_polling(
                poll_interval=1,
                request_timeout=50,   # PTB ≥21
                stop_signals=None,
            )
        except TypeError:
            application.run_polling(  # PTB 20.x
                poll_interval=1,
                stop_signals=None,
            )

    threading.Thread(target=_run, daemon=True).start()