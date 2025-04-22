import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = max(2, multiprocessing.cpu_count() * 2 + 1)
threads = 2
timeout = 120
loglevel = "info"
accesslog = "-"
errorlog = "-"