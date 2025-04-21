"""
Gunicorn‑конфигурация.

После старта воркера мы создаём отдельный поток и в нём запускаем
Telegram‑бота (polling).  В потоке вручную создаётся asyncio‑loop,
чтобы run_polling() у PTB 20.x не упал с RuntimeError.
"""

import os
import threading
import logging
import asyncio

bind          = f"0.0.0.0:{os.getenv('PORT', 8000)}"
worker_class  = "gthread"
workers       = 1
threads       = 4
timeout       = 0          # бесконечный hard‑timeout
keepalive     = 5

wsgi_app = "bot:flask_app"

def post_fork(server, worker):
    """После форка (запуска воркера) стартуем polling‑бота."""
    from bot import application                      # noqa: WPS433
    log = logging.getLogger("gunicorn.post_fork")
    log.info("post_fork: запускаем Telegram‑бот (PID %s)", worker.pid)

    def _run() -> None:
        # ───── создаём event‑loop для потока ─────
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # ───── запускаем polling ─────
        try:
            # PTB ≥ 21 (имеет request_timeout)
            application.run_polling(
                poll_interval=1,
                request_timeout=50,
                stop_signals=None,
            )
        except TypeError:
            # PTB 20.x – запускаем без request_timeout
            application.run_polling(
                poll_interval=1,
                stop_signals=None,
            )

    threading.Thread(target=_run, daemon=True).start()