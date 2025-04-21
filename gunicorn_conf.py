"""
Gunicorn configuration

1. gthread‑worker + 4 threads             → long‑poll не мешает health‑check’у
2. bind на $PORT                          → Render пробьёт контейнер
3. Null WSGI‑app, отвечающий «OK»         → health‑check < 1 мс
4. post_fork запускает run_bot() в явном
   отдельном треде после форка воркера    → 409 Conflict исключён
"""

import os
import threading

# ──────────────────────────────────────────
# Основные параметры Gunicorn
# ──────────────────────────────────────────
bind          = f'0.0.0.0:{os.getenv("PORT", 10000)}'
worker_class  = 'gthread'
workers       = 1          # нужен только один, polling сам по себе
threads       = 4          # 1 поток держит long‑poll, остальные свободны
timeout       = 0          # нет запроса – нет таймаута
keepalive     = 5

# ──────────────────────────────────────────
# WSGI‑приложение‑заглушка для Render
# ──────────────────────────────────────────
def app(environ, start_response):
    """Минимальное WSGI‑“Hello, world” → всегда ‘200 OK’."""
    body = b'OK'
    start_response('200 OK', [
        ('Content-Type',   'text/plain'),
        ('Content-Length', str(len(body)))
    ])
    return [body]

wsgi_app = 'gunicorn_conf:app'   # отсылаем Gunicorn на функцию выше

# ──────────────────────────────────────────
# Старт Telegram‑бота после форка воркера
# ──────────────────────────────────────────
def post_fork(server, worker):
    from bot import run_bot               # импортируем только внутри воркера
    worker.log.info('>> post_fork: стартуем Telegram‑бот (PID %s)', worker.pid)
    threading.Thread(target=run_bot, daemon=True).start()