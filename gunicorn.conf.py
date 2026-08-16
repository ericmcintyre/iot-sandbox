import os

bind = f"0.0.0.0:{os.environ.get('GUNICORN_PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
accesslog = "-"
errorlog = "-"
