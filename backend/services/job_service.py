"""
services/job_service.py — Phase 2

Public API (called by routers):
    create_batch(images, transformations)   async — validates, saves files, writes Redis
    dispatch_tasks(batch_id, filenames, transformations)  — writes task hashes, dispatches Celery
    get_batch_status(batch_id)              → BatchStatusResponse
    get_batch_results(batch_id)             → BatchResultsResponse

Internal / test helper (no file I/O, no Celery):
    init_batch_record(filenames, transformations, *, redis_url) → (batch_id, total)
    Used by test_redis_state.py AC-2.1 / AC-2.2 to seed Redis directly.
"""
import json
import os
import pathlib
import uuid
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import HTTPException, UploadFile

from core.config import settings
from core.logger import get_logger
from core.redis_client import (
    append_task_to_batch,
    get_all_tasks_for_batch,
    get_batch_meta,
    redis_client,
    set_batch_meta,
    set_task,
)
from models.schemas import (
    BatchResultsResponse,
    BatchStatusResponse,
    BenchmarkData,
    ImageResult,
    TaskSummary,
)

logger = get_logger(__name__)

_VALID_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Internal helper — no file I/O, no Celery; redirectable to test DB via redis_url
# Used by test_redis_state.py AC-2.1 to seed Redis without UploadFile objects.
# ---------------------------------------------------------------------------

def init_batch_record(
    filenames: list[str],
    transformations: list[str],
    *,
    redis_url: str | None = None,
) -> tuple[str, int]:
    """Writes batch meta Hash to Redis. Returns (batch_id, total)."""
    batch_id = str(uuid.uuid4())
    total = len(filenames)
    set_batch_meta(
        batch_id,
        {
            "batch_id": batch_id,
            "status": "QUEUED",
            "total": total,
            "completed": 0,
            "failed": 0,
            "transformations": json.dumps(transformations),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": "",
            "completed_at": "",
        },
        redis_url=redis_url,
    )
    return batch_id, total


# ---------------------------------------------------------------------------
# Phase 2 — batch creation (file I/O + Redis)
# ---------------------------------------------------------------------------

async def create_batch(
    images: list[UploadFile],
    transformations: list[str],
) -> dict:
    """
    Validates each image (format + size), saves to UPLOAD_DIR/{batch_id}/,
    writes batch meta to Redis. Raises HTTPException 422 on validation failure.
    Returns {batch_id, total_images, filenames}.
    """
    if not images:
        raise HTTPException(status_code=422, detail="At least one image is required.")

    # Validate all files before saving any — avoid partial batch state on failure.
    validated: list[tuple[str, bytes]] = []
    for img in images:
        filename = img.filename or ""
        ext = pathlib.Path(filename).suffix.lower()

        if ext not in _VALID_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unsupported file format '{ext}' for '{filename}'. "
                    "Accepted formats: jpg, jpeg, png, webp."
                ),
            )

        content = await img.read()

        if len(content) > _MAX_SIZE_BYTES:
            size_mb = len(content) / (1024 * 1024)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"File '{filename}' is {size_mb:.1f} MB — exceeds the 5 MB per-file limit."
                ),
            )

        validated.append((filename, content))

    batch_id = str(uuid.uuid4())
    batch_upload_dir = pathlib.Path(settings.UPLOAD_DIR) / batch_id
    batch_upload_dir.mkdir(parents=True, exist_ok=True)

    filenames: list[str] = []
    for filename, content in validated:
        (batch_upload_dir / filename).write_bytes(content)
        filenames.append(filename)

    created_at = datetime.now(timezone.utc).isoformat()
    set_batch_meta(
        batch_id,
        {
            "batch_id": batch_id,
            "status": "QUEUED",
            "total": len(filenames),
            "completed": 0,
            "failed": 0,
            "transformations": json.dumps(transformations),
            "created_at": created_at,
            "started_at": "",
            "completed_at": "",
        },
    )

    logger.info("batch created", extra={"batch_id": batch_id, "total": len(filenames)})
    return {"batch_id": batch_id, "total_images": len(filenames), "filenames": filenames}


# ---------------------------------------------------------------------------
# Task dispatch — writes task hashes + dispatches Celery tasks
# ---------------------------------------------------------------------------

def dispatch_tasks(
    batch_id: str,
    filenames: list[str],
    transformations: list[str],
    *,
    redis_url: str | None = None,
) -> list[str]:
    """
    For each filename: writes task Hash to Redis, appends task_id to batch list.
    In production (redis_url=None): dispatches process_image.delay() per task.
    In test mode (redis_url set): skips Celery dispatch — no broker required.
    Returns list of task_ids.
    """
    # Deferred import prevents circular dependency (tasks imports celery_app imports nothing here).
    from tasks.image_tasks import process_image  # noqa: PLC0415

    rc = (
        redis_lib.Redis.from_url(redis_url, decode_responses=True)
        if redis_url is not None
        else redis_client
    )

    queued_at = datetime.now(timezone.utc).isoformat()
    task_ids: list[str] = []

    for filename in filenames:
        task_id = str(uuid.uuid4())
        p = pathlib.Path(filename)
        upload_path = str(pathlib.Path(settings.UPLOAD_DIR) / batch_id / filename)
        output_dir = str(pathlib.Path(settings.OUTPUT_DIR) / batch_id)
        output_path = str(pathlib.Path(output_dir) / f"{p.stem}_processed{p.suffix}")

        set_task(
            task_id,
            {
                "task_id": task_id,
                "batch_id": batch_id,
                "filename": filename,
                "status": "QUEUED",
                "worker_id": "",
                "attempt": 1,
                "original_path": upload_path,
                "output_path": "",
                "original_size_kb": _file_size_kb(upload_path),
                "output_size_kb": 0,
                "duration_ms": 0,
                "error": "",
                "queued_at": queued_at,
                "started_at": "",
                "completed_at": "",
                "transformations": json.dumps(transformations),
            },
            redis_url=redis_url,
        )
        append_task_to_batch(batch_id, task_id, redis_url=redis_url)
        task_ids.append(task_id)

        if redis_url is None:
            process_image.delay(task_id, batch_id, filename, transformations)

    # Mark batch PROCESSING; started_at records dispatch time.
    # Workers use HSETNX so they will not overwrite this value.
    rc.hset(
        f"batch:{batch_id}:meta",
        mapping={
            "status": "PROCESSING",
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    logger.info(
        "tasks dispatched",
        extra={"batch_id": batch_id, "task_count": len(task_ids)},
    )
    return task_ids


def _file_size_kb(path: str) -> int:
    try:
        return (os.path.getsize(path) + 1023) // 1024
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Status + results queries
# ---------------------------------------------------------------------------

def get_batch_status(batch_id: str) -> BatchStatusResponse:
    """
    Reads batch meta + all task hashes. Raises 404 if batch unknown.
    Computes elapsed_ms and throughput from created_at.
    """
    meta = get_batch_meta(batch_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    tasks_data = get_all_tasks_for_batch(batch_id)

    created_at = datetime.fromisoformat(meta["created_at"])
    now = datetime.now(timezone.utc)
    elapsed_ms = max(0, int((now - created_at).total_seconds() * 1000))

    completed = int(meta.get("completed", 0))
    elapsed_s = elapsed_ms / 1000
    throughput = round(completed / elapsed_s, 3) if elapsed_s > 0 else 0.0

    tasks = [
        TaskSummary(
            task_id=t["task_id"],
            filename=t["filename"],
            status=t["status"],
            worker_id=t.get("worker_id", ""),
            duration_ms=int(t.get("duration_ms", 0)),
            error=t.get("error", ""),
        )
        for t in tasks_data
    ]

    return BatchStatusResponse(
        batch_id=batch_id,
        status=meta["status"],
        total=int(meta.get("total", 0)),
        completed=completed,
        failed=int(meta.get("failed", 0)),
        elapsed_ms=elapsed_ms,
        throughput=throughput,
        tasks=tasks,
    )


def get_batch_results(batch_id: str) -> BatchResultsResponse:
    """
    Reads all task hashes, builds ImageResult list, computes BenchmarkData.
    Raises 404 if batch unknown.
    """
    meta = get_batch_meta(batch_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    tasks_data = get_all_tasks_for_batch(batch_id)
    transformations_applied: list[str] = json.loads(meta.get("transformations", "[]"))

    images: list[ImageResult] = []
    for t in tasks_data:
        filename = t["filename"]
        p = pathlib.Path(filename)
        original_url = f"/uploads/{batch_id}/{filename}"
        processed_url = (
            f"/outputs/{batch_id}/{p.stem}_processed{p.suffix}"
            if t.get("status") == "SUCCESS"
            else ""
        )
        images.append(
            ImageResult(
                task_id=t["task_id"],
                filename=filename,
                status=t["status"],
                worker_id=t.get("worker_id", ""),
                duration_ms=int(t.get("duration_ms", 0)),
                original_size_kb=int(t.get("original_size_kb", 0)),
                output_size_kb=int(t.get("output_size_kb", 0)),
                original_url=original_url,
                processed_url=processed_url,
                transformations_applied=transformations_applied,
            )
        )

    # Benchmark — DATA-MODEL §3.2 BenchmarkData
    # Failed tasks have duration_ms=0, so they contribute 0 to the sum (excluded naturally).
    sequential_estimate_ms = sum(int(t.get("duration_ms", 0)) for t in tasks_data)
    two_worker_estimate_ms = sequential_estimate_ms // 2

    started_at_str = meta.get("started_at", "")
    completed_at_str = meta.get("completed_at", "")
    if started_at_str and completed_at_str:
        started_at = datetime.fromisoformat(started_at_str)
        completed_at_dt = datetime.fromisoformat(completed_at_str)
        actual_ms = max(1, int((completed_at_dt - started_at).total_seconds() * 1000))
    else:
        actual_ms = max(1, sequential_estimate_ms)

    speedup_factor = round(sequential_estimate_ms / actual_ms, 2) if actual_ms > 0 else 1.0

    benchmark = BenchmarkData(
        sequential_estimate_ms=sequential_estimate_ms,
        two_worker_estimate_ms=two_worker_estimate_ms,
        actual_ms=actual_ms,
        speedup_factor=speedup_factor,
    )

    return BatchResultsResponse(
        batch_id=batch_id,
        status=meta["status"],
        images=images,
        benchmark=benchmark,
    )
