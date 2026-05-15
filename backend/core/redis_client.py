"""
Singleton Redis connection + typed helper functions.
All key patterns are canonical — defined here, nowhere else.

Functions accept an optional redis_url kwarg so tests can redirect to DB 1
without touching module-level state.
"""
import json
from typing import Any

import redis

from core.config import settings


def _get_client(redis_url: str | None = None) -> redis.Redis:
    if redis_url is not None:
        return redis.Redis.from_url(redis_url, decode_responses=True)
    return redis_client


# Module-level singleton — used by all production code.
redis_client: redis.Redis = redis.Redis.from_url(
    settings.REDIS_URL, decode_responses=True
)

_BATCH_TTL = 86400
_WORKER_TTL = 30


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def set_batch_meta(batch_id: str, data: dict, *, redis_url: str | None = None) -> None:
    rc = _get_client(redis_url)
    key = f"batch:{batch_id}:meta"
    rc.hset(key, mapping=data)
    rc.expire(key, _BATCH_TTL)


def get_batch_meta(batch_id: str, *, redis_url: str | None = None) -> dict:
    rc = _get_client(redis_url)
    return rc.hgetall(f"batch:{batch_id}:meta")


def append_task_to_batch(batch_id: str, task_id: str, *, redis_url: str | None = None) -> None:
    rc = _get_client(redis_url)
    key = f"batch:{batch_id}:tasks"
    rc.rpush(key, task_id)
    rc.expire(key, _BATCH_TTL)


def get_batch_task_ids(batch_id: str, *, redis_url: str | None = None) -> list[str]:
    rc = _get_client(redis_url)
    return rc.lrange(f"batch:{batch_id}:tasks", 0, -1)


def increment_batch_completed(batch_id: str, *, redis_url: str | None = None) -> int:
    rc = _get_client(redis_url)
    return rc.hincrby(f"batch:{batch_id}:meta", "completed", 1)


def increment_batch_failed(batch_id: str, *, redis_url: str | None = None) -> int:
    rc = _get_client(redis_url)
    return rc.hincrby(f"batch:{batch_id}:meta", "failed", 1)


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def set_task(task_id: str, data: dict, *, redis_url: str | None = None) -> None:
    rc = _get_client(redis_url)
    key = f"task:{task_id}"
    rc.hset(key, mapping=data)
    rc.expire(key, _BATCH_TTL)


def get_task(task_id: str, *, redis_url: str | None = None) -> dict:
    rc = _get_client(redis_url)
    return rc.hgetall(f"task:{task_id}")


def get_all_tasks_for_batch(batch_id: str, *, redis_url: str | None = None) -> list[dict]:
    rc = _get_client(redis_url)
    task_ids = rc.lrange(f"batch:{batch_id}:tasks", 0, -1)
    tasks = []
    for tid in task_ids:
        task = rc.hgetall(f"task:{tid}")
        if task:
            tasks.append(task)
    return tasks


# ---------------------------------------------------------------------------
# Worker helpers
# ---------------------------------------------------------------------------

def set_worker_status(worker_id: str, data: dict, *, redis_url: str | None = None) -> None:
    rc = _get_client(redis_url)
    key = f"worker:{worker_id}:status"
    rc.hset(key, mapping=data)
    rc.expire(key, _WORKER_TTL)


def register_worker(worker_id: str, *, redis_url: str | None = None) -> None:
    rc = _get_client(redis_url)
    rc.sadd("workers:registry", worker_id)


def get_all_worker_statuses(*, redis_url: str | None = None) -> list[dict]:
    rc = _get_client(redis_url)
    known = rc.smembers("workers:registry")
    if not known:
        # Fallback: scan for any live keys (e.g. before registry is populated)
        for key in rc.scan_iter("worker:*:status"):
            data = rc.hgetall(key)
            if data:
                known.add(data.get("worker_id", ""))

    statuses = []
    for worker_id in sorted(known):
        if not worker_id:
            continue
        data = rc.hgetall(f"worker:{worker_id}:status")
        if data:
            statuses.append(data)
        else:
            statuses.append({
                "worker_id": worker_id,
                "status": "OFFLINE",
                "current_filename": "",
                "tasks_completed": 0,
                "tasks_failed": 0,
                "last_heartbeat": "",
            })
    return statuses


# ---------------------------------------------------------------------------
# SSE event stream helpers
# ---------------------------------------------------------------------------

def push_stream_event(batch_id: str, event: dict[str, Any], *, redis_url: str | None = None) -> None:
    rc = _get_client(redis_url)
    rc.rpush(f"stream:{batch_id}:events", json.dumps(event))


def pop_stream_event(batch_id: str, timeout: int = 15, *, redis_url: str | None = None) -> dict | None:
    rc = _get_client(redis_url)
    result = rc.blpop(f"stream:{batch_id}:events", timeout=timeout)
    if result is None:
        return None
    _key, raw = result
    return json.loads(raw)
