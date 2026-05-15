import json
import uuid
from datetime import datetime, timezone

from core.redis_client import append_task_to_batch, set_batch_meta, set_task


def create_batch(
    filenames: list[str],
    transformations: list[str],
    *,
    redis_url: str | None = None,
) -> tuple[str, int]:
    batch_id = str(uuid.uuid4())
    total = len(filenames)
    set_batch_meta(
        batch_id,
        {
            "status": "QUEUED",
            "total": total,
            "completed": 0,
            "failed": 0,
            "transformations": json.dumps(transformations),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        redis_url=redis_url,
    )
    return batch_id, total


def dispatch_tasks(
    batch_id: str,
    filenames: list[str],
    transformations: list[str],
    *,
    redis_url: str | None = None,
) -> list[str]:
    task_ids = []
    for filename in filenames:
        task_id = str(uuid.uuid4())
        set_task(
            task_id,
            {
                "task_id": task_id,
                "batch_id": batch_id,
                "filename": filename,
                "status": "QUEUED",
                "worker_id": "",
                "duration_ms": 0,
                "output_size_kb": 0,
                "error": "",
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "started_at": "",
                "completed_at": "",
                "output_path": "",
                "transformations": json.dumps(transformations),
            },
            redis_url=redis_url,
        )
        append_task_to_batch(batch_id, task_id, redis_url=redis_url)
        task_ids.append(task_id)
    return task_ids
