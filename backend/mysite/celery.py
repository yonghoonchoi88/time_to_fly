"""Celery application for background work (calls to the AI inference server).

Start a worker with ``celery -A mysite worker --loglevel=info``. Every setting is read
from Django settings under the ``CELERY_`` prefix, so there is one place to configure it.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

app = Celery("mysite")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
