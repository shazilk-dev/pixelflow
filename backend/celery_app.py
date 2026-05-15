from celery import Celery

from core.config import settings

celery_app = Celery("pipeline", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_acks_late=True,              # fault-tolerance: keeps task in queue until worker confirms
    worker_prefetch_multiplier=1,     # load-balancing: forces 1 task at a time per worker
    task_reject_on_worker_lost=True,  # re-queue task when worker process dies unexpectedly
    task_max_retries=3,
    task_retry_backoff=True,          # exponential backoff: 1s, 2s, 4s
    task_retry_backoff_max=10,        # cap backoff at 10s
    result_expires=86400,
)

celery_app.conf.include = ["tasks.image_tasks"]
