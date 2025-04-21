"""
Gunicorn config: запускаем polling‑бота ТОЛЬКО в воркер‑процессе
(после форка). Мастер‑процесс бота не трогает → 409 Conflict нет.
"""

def post_fork(server, worker):
    from bot import run_bot
    worker.log.info(">> post_fork: стартуем Telegram‑бот в PID %s",
                    worker.pid)
    import threading
    threading.Thread(target=run_bot, daemon=True).start()