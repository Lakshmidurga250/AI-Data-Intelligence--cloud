"""Celery application instance configuration for async background task execution."""

import os
from celery import Celery

from app.core.config import settings

# Initialize Celery app
celery_app = Celery(
    "ai_data_cloud_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
)

# In test/development environment without Redis daemon, support eager execution mode
if os.getenv("CELERY_ALWAYS_EAGER", "true").lower() in ("true", "1", "yes"):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
