"""
NAADAMAYA Celery application.

The worker is started by docker-compose with:

    celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --concurrency=2

Design choices:
  - Redis is both the broker and the result backend (REDIS_URL).
  - task_acks_late: a task is acknowledged only AFTER it finishes, so if the
    worker crashes mid-analysis the task is delivered again instead of lost.
    The analysis task is idempotent (it checks the analysis status first, and
    credits are protected by unique ledger keys), so a re-run is safe.
  - worker_prefetch_multiplier=1: a worker takes one heavy audio job at a
    time, so a long analysis does not hold other jobs hostage.
  - Hard and soft time limits stop a stuck analysis from running forever.
  - Two queues: "analysis" (normal) and "analysis_priority" (for plans with
    the priority_processing flag, e.g. PRO). The worker listens to both and
    drains the priority queue first.
  - Pitch tracking is CPU-heavy. Keep --concurrency at or below your CPU
    cores, and remember each task loads two recordings into memory.

Logging is configured at worker start so worker logs use the same redacted,
request-aware format as the API.
"""

from celery import Celery
from celery.signals import setup_logging
from kombu import Exchange, Queue

from app.core.config import settings
from app.core.logging import setup_logging as configure_app_logging

ANALYSIS_QUEUE = "analysis"
PRIORITY_QUEUE = "analysis_priority"

celery_app = Celery(
    "naadamaya",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.analysis_worker"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Do not keep results around: the database is the source of truth.
    result_expires=3600,
    task_ignore_result=True,
    # Limits (seconds). Soft limit raises inside the task so it can fail cleanly.
    task_soft_time_limit=20 * 60,
    task_time_limit=22 * 60,
    # Queues
    task_default_queue=ANALYSIS_QUEUE,
    task_queues=(
        Queue(PRIORITY_QUEUE, Exchange(PRIORITY_QUEUE), routing_key=PRIORITY_QUEUE),
        Queue(ANALYSIS_QUEUE, Exchange(ANALYSIS_QUEUE), routing_key=ANALYSIS_QUEUE),
    ),
    task_routes={"naadamaya.run_analysis": {"queue": ANALYSIS_QUEUE}},
    # Memory: restart a worker process after a number of tasks (audio libraries can leak).
    worker_max_tasks_per_child=20,
)


@setup_logging.connect
def _configure_logging(**_kwargs) -> None:
    """Use NAADAMAYA's logging instead of Celery's default."""
    configure_app_logging()
