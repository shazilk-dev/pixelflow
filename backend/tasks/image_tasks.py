"""
Core Celery task: process_image
Worker lifecycle: heartbeat_loop, listen_for_control_signals, boot_worker_threads

REF: DATA-MODEL.md Section 2.3, 4.1, 4.3, 7
REF: ARCHITECTURE.md Section 3 Flow D
REF: CLAUDE.md Kill Worker implementation
"""
import json
import os
import pathlib
import threading
import time
from datetime import datetime, timezone

import redis as redis_lib
from celery.exceptions import MaxRetriesExceededError
from celery.signals import worker_init
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from celery_app import celery_app
from core.config import settings
from core.logger import get_logger
from core.redis_client import push_stream_event

logger = get_logger(__name__)

WORKER_ID: str = os.getenv("WORKER_ID", "")

# Canonical transformation order — never change this order.
# DATA-MODEL.md Section 7: resize → grayscale → blur → sharpen → watermark
CANONICAL_ORDER: list[str] = ["resize", "grayscale", "blur", "sharpen", "watermark"]

# Shared state read by the heartbeat daemon thread.
# Safe under GIL for dict updates + reads (no explicit lock needed).
_worker_state: dict = {
    "status": "IDLE",
    "current_task_id": "",
    "current_filename": "",
    "current_batch_id": "",
    "tasks_completed": 0,
    "tasks_failed": 0,
}


# ---------------------------------------------------------------------------
# Internal Redis helper — lets test functions redirect to DB 1
# ---------------------------------------------------------------------------

def _get_redis(redis_url: str | None) -> redis_lib.Redis:
    if redis_url is not None:
        return redis_lib.Redis.from_url(redis_url, decode_responses=True)
    from core.redis_client import redis_client  # noqa: PLC0415
    return redis_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Image transformation helpers (exported — tests import these directly)
# ---------------------------------------------------------------------------

def build_output_path(input_path: str, output_dir: str) -> str:
    """Returns the canonical output path: {output_dir}/{stem}_processed{ext}."""
    p = pathlib.Path(input_path)
    return str(pathlib.Path(output_dir) / f"{p.stem}_processed{p.suffix}")


def _draw_watermark(img: Image.Image) -> None:
    """Draws 'Processed by DPC Pipeline' text in the bottom-right quadrant."""
    draw = ImageDraw.Draw(img)
    text = "Processed by DPC Pipeline"
    font = ImageFont.load_default()
    w, h = img.size
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        # Pillow < 9.2 fallback
        text_w = len(text) * 6
        text_h = 11
    x = max(0, w - text_w - 10)
    y = max(0, h - text_h - 10)
    draw.text((x, y), text, fill=(64, 64, 64), font=font)


def apply_transforms(input_path: str, output_path: str, transformations: list[str]) -> None:
    """
    Applies transformations in canonical order: resize→grayscale→blur→sharpen→watermark.
    Handles the grayscale+watermark edge case: re-converts to RGB before drawing.
    Uses a context manager for Image.open so the file descriptor is closed after processing.
    """
    ordered = [t for t in CANONICAL_ORDER if t in transformations]

    with Image.open(input_path) as img:
        # Normalise exotic modes (CMYK, P, RGBA) to RGB before processing.
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        for transform in ordered:
            if transform == "resize":
                img = img.resize((800, 600), resample=Image.LANCZOS)
            elif transform == "grayscale":
                img = img.convert("L")
            elif transform == "blur":
                img = img.filter(ImageFilter.GaussianBlur(radius=2))
            elif transform == "sharpen":
                img = img.filter(ImageFilter.SHARPEN)
            elif transform == "watermark":
                # PIL cannot draw text on "L" (single-channel) mode images.
                # Re-convert to RGB first — this is the documented edge case.
                if img.mode != "RGB":
                    img = img.convert("RGB")
                _draw_watermark(img)

        img.save(output_path)


# ---------------------------------------------------------------------------
# Redis state helpers (exported — tests import these directly)
# ---------------------------------------------------------------------------

def update_task_processing(
    task_id: str,
    worker_id: str,
    *,
    attempt: int = 1,
    redis_url: str | None = None,
) -> None:
    rc = _get_redis(redis_url)
    rc.hset(f"task:{task_id}", mapping={
        "status": "PROCESSING",
        "worker_id": worker_id,
        "attempt": attempt,
        "started_at": _now_iso(),
    })


def update_task_success(
    task_id: str,
    batch_id: str,
    output_path: str,
    duration_ms: int,
    *,
    redis_url: str | None = None,
) -> int:
    """Updates task → SUCCESS, increments batch.completed. Returns the new completed count."""
    rc = _get_redis(redis_url)
    size_bytes = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    # Ceiling division: ensures even tiny files report ≥1 KB rather than 0.
    output_size_kb = (size_bytes + 1023) // 1024

    with rc.pipeline() as pipe:
        pipe.hset(f"task:{task_id}", mapping={
            "status": "SUCCESS",
            "duration_ms": duration_ms,
            "output_size_kb": output_size_kb,
            "output_path": output_path,
            "completed_at": _now_iso(),
        })
        pipe.hincrby(f"batch:{batch_id}:meta", "completed", 1)
        results = pipe.execute()

    return int(results[1])  # new value from HINCRBY


def update_task_failed(
    task_id: str,
    batch_id: str,
    error_message: str,
    *,
    redis_url: str | None = None,
) -> int:
    """Updates task → FAILED, increments batch.failed. Returns the new failed count."""
    rc = _get_redis(redis_url)

    with rc.pipeline() as pipe:
        pipe.hset(f"task:{task_id}", mapping={
            "status": "FAILED",
            "error": error_message,
            "duration_ms": 0,
            "completed_at": _now_iso(),
        })
        pipe.hincrby(f"batch:{batch_id}:meta", "failed", 1)
        results = pipe.execute()

    return int(results[1])


def send_heartbeat(
    worker_id: str,
    status: str,
    *,
    current_task_id: str = "",
    current_filename: str = "",
    tasks_completed: int = 0,
    tasks_failed: int = 0,
    redis_url: str | None = None,
) -> None:
    """Writes worker status Hash and sets TTL=30s. Called every 2s by heartbeat_loop."""
    rc = _get_redis(redis_url)
    key = f"worker:{worker_id}:status"
    rc.hset(key, mapping={
        "worker_id": worker_id,
        "status": status,
        "current_task_id": current_task_id,
        "current_filename": current_filename,
        "tasks_completed": tasks_completed,
        "tasks_failed": tasks_failed,
        "last_heartbeat": _now_iso(),
    })
    rc.expire(key, 30)


# ---------------------------------------------------------------------------
# SSE event helpers (internal)
# ---------------------------------------------------------------------------

def _push_task_update_event(
    task_id: str,
    batch_id: str,
    filename: str,
    status: str,
    worker_id: str,
    duration_ms: int,
    attempt: int,
    error: str,
) -> None:
    """Pushes a task_update event to stream:{batch_id}:events. DATA-MODEL §4.1."""
    push_stream_event(batch_id, {
        "event": "task_update",
        "task_id": task_id,
        "batch_id": batch_id,
        "filename": filename,
        "status": status,
        "worker_id": worker_id,
        "duration_ms": duration_ms,
        "attempt": attempt,
        "error": error,
    })


def _check_and_emit_batch_complete(batch_id: str) -> None:
    """
    Called after every task success or permanent failure.
    If completed + failed == total, one worker claims the role (SETNX lock)
    and emits the batch_complete SSE event. DATA-MODEL §4.3.
    """
    from core.redis_client import redis_client as rc  # noqa: PLC0415

    meta = rc.hgetall(f"batch:{batch_id}:meta")
    total = int(meta.get("total", 0))
    completed = int(meta.get("completed", 0))
    failed = int(meta.get("failed", 0))

    if total == 0 or (completed + failed) < total:
        return

    # Atomic claim — prevents two workers both emitting batch_complete.
    claimed = rc.set(f"batch:{batch_id}:complete_claimed", "1", nx=True, ex=86400)
    if not claimed:
        return

    # Sum durations of all tasks. Failed tasks have duration_ms=0 — excluded naturally.
    task_ids = rc.lrange(f"batch:{batch_id}:tasks", 0, -1)
    sequential_estimate_ms = sum(
        int(rc.hget(f"task:{tid}", "duration_ms") or 0)
        for tid in task_ids
    )

    started_at_str = meta.get("started_at", "")
    completed_at = datetime.now(timezone.utc)
    if started_at_str:
        started_at = datetime.fromisoformat(started_at_str)
        actual_ms = max(1, int((completed_at - started_at).total_seconds() * 1000))
    else:
        actual_ms = max(1, sequential_estimate_ms)

    speedup_factor = round(sequential_estimate_ms / actual_ms, 2) if actual_ms > 0 else 1.0

    batch_status = "COMPLETE" if failed == 0 else "PARTIAL_FAILURE"
    rc.hset(f"batch:{batch_id}:meta", mapping={
        "status": batch_status,
        "completed_at": completed_at.isoformat(),
    })

    push_stream_event(batch_id, {
        "event": "batch_complete",
        "batch_id": batch_id,
        "total": total,
        "completed": completed,
        "failed": failed,
        "actual_ms": actual_ms,
        "sequential_estimate_ms": sequential_estimate_ms,
        "speedup_factor": speedup_factor,
    })

    logger.info(
        "batch_complete emitted",
        extra={"batch_id": batch_id, "speedup_factor": speedup_factor},
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="tasks.process_image",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_image(
    self,
    task_id: str,
    batch_id: str,
    filename: str,
    transformations: list[str],
) -> dict:
    from core.redis_client import redis_client as rc  # noqa: PLC0415

    start_ms = time.monotonic()
    attempt = self.request.retries + 1

    # --- Mark PROCESSING ---
    update_task_processing(task_id, WORKER_ID, attempt=attempt)
    _push_task_update_event(task_id, batch_id, filename, "PROCESSING", WORKER_ID, 0, attempt, "")

    # First worker to pick up a task sets batch.started_at (HSETNX is atomic).
    rc.hsetnx(f"batch:{batch_id}:meta", "started_at", _now_iso())
    rc.hset(f"batch:{batch_id}:meta", "status", "PROCESSING")

    _worker_state.update({
        "status": "PROCESSING",
        "current_task_id": task_id,
        "current_filename": filename,
        "current_batch_id": batch_id,
    })

    # Push immediately — don't wait for the 2s heartbeat (tasks often finish faster).
    push_stream_event(batch_id, {
        "event": "worker_status",
        "worker_id": WORKER_ID,
        "status": "PROCESSING",
        "current_filename": filename,
        "tasks_completed": _worker_state["tasks_completed"],
        "tasks_failed": _worker_state["tasks_failed"],
    })

    try:
        upload_path = os.path.join(settings.UPLOAD_DIR, batch_id, filename)
        output_dir = os.path.join(settings.OUTPUT_DIR, batch_id)
        os.makedirs(output_dir, exist_ok=True)
        output_path = build_output_path(upload_path, output_dir)

        apply_transforms(upload_path, output_path, transformations)

        duration_ms = int((time.monotonic() - start_ms) * 1000)
        update_task_success(task_id, batch_id, output_path, duration_ms)
        _push_task_update_event(
            task_id, batch_id, filename, "SUCCESS", WORKER_ID, duration_ms, attempt, ""
        )

        _worker_state["tasks_completed"] += 1
        _worker_state.update({
            "status": "IDLE",
            "current_task_id": "",
            "current_filename": "",
            "current_batch_id": "",
        })

        push_stream_event(batch_id, {
            "event": "worker_status",
            "worker_id": WORKER_ID,
            "status": "IDLE",
            "current_filename": "",
            "tasks_completed": _worker_state["tasks_completed"],
            "tasks_failed": _worker_state["tasks_failed"],
        })

        _check_and_emit_batch_complete(batch_id)

        logger.info("task SUCCESS", extra={"task_id": task_id, "duration_ms": duration_ms})
        return {"task_id": task_id, "status": "SUCCESS", "duration_ms": duration_ms}

    except Exception as exc:
        logger.error(
            "task error", extra={"task_id": task_id, "attempt": attempt, "error": str(exc)}
        )
        try:
            raise self.retry(exc=exc, countdown=min(2 ** self.request.retries, 10))
        except MaxRetriesExceededError:
            update_task_failed(task_id, batch_id, str(exc))
            _push_task_update_event(task_id, batch_id, filename, "FAILED", WORKER_ID, 0, attempt, str(exc))
            _worker_state["tasks_failed"] += 1
            _worker_state.update({
                "status": "IDLE",
                "current_task_id": "",
                "current_filename": "",
                "current_batch_id": "",
            })

            push_stream_event(batch_id, {
                "event": "worker_status",
                "worker_id": WORKER_ID,
                "status": "IDLE",
                "current_filename": "",
                "tasks_completed": _worker_state["tasks_completed"],
                "tasks_failed": _worker_state["tasks_failed"],
            })

            _check_and_emit_batch_complete(batch_id)
            logger.error("task FAILED (max retries exhausted)", extra={"task_id": task_id})
            return {"task_id": task_id, "status": "FAILED"}


# ---------------------------------------------------------------------------
# Worker thread functions
# ---------------------------------------------------------------------------

def heartbeat_loop(worker_id: str) -> None:
    """
    Daemon thread: refreshes worker:{worker_id}:status every 2s with TTL=30s.
    Also pushes worker_status SSE events while a batch is active.
    TTL=30s is the dead-man switch — expired key = OFFLINE on dashboard.
    """
    from core.redis_client import redis_client as rc  # noqa: PLC0415

    while True:
        state = _worker_state.copy()
        current_batch_id = state["current_batch_id"]

        key = f"worker:{worker_id}:status"
        rc.hset(key, mapping={
            "worker_id": worker_id,
            "status": state["status"],
            "current_task_id": state["current_task_id"],
            "current_filename": state["current_filename"],
            "tasks_completed": state["tasks_completed"],
            "tasks_failed": state["tasks_failed"],
            "last_heartbeat": _now_iso(),
        })
        rc.expire(key, 30)

        if current_batch_id:
            push_stream_event(current_batch_id, {
                "event": "worker_status",
                "worker_id": worker_id,
                "status": state["status"],
                "current_filename": state["current_filename"],
                "tasks_completed": state["tasks_completed"],
                "tasks_failed": state["tasks_failed"],
            })

        time.sleep(2)


def listen_for_control_signals(worker_id: str) -> None:
    """
    Daemon thread: blocking pub/sub loop on channel:worker_control.
    Calls os._exit(1) on a matching kill signal — hard crash bypasses
    Python's graceful shutdown so Celery's task_acks_late re-queues the task.
    MUST NOT be called on the main thread — pubsub.listen() blocks forever.
    """
    from core.redis_client import redis_client as rc  # noqa: PLC0415

    pubsub = rc.pubsub()
    pubsub.subscribe("channel:worker_control")
    logger.info("subscribed to worker_control", extra={"worker_id": worker_id})

    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("action") == "kill" and data.get("target") == worker_id:
            logger.info("kill signal received — calling os._exit(1)", extra={"worker_id": worker_id})
            os._exit(1)


def boot_worker_threads(worker_id: str) -> None:
    """
    Starts heartbeat and pub/sub listener as daemon threads.
    Worker ID is always read from env — never parsed from hostname or sys.argv.
    Called via the Celery worker_init signal so threads start before any task is consumed.
    """
    from core.redis_client import register_worker  # noqa: PLC0415
    register_worker(worker_id)

    threading.Thread(
        target=heartbeat_loop,
        args=(worker_id,),
        daemon=True,
        name=f"heartbeat-{worker_id}",
    ).start()

    threading.Thread(
        target=listen_for_control_signals,
        args=(worker_id,),
        daemon=True,
        name=f"pubsub-{worker_id}",
    ).start()

    logger.info("worker threads started", extra={"worker_id": worker_id})


# ---------------------------------------------------------------------------
# Celery signal — boot threads on worker startup
# ---------------------------------------------------------------------------

@worker_init.connect
def on_worker_init(sender, **kwargs) -> None:
    worker_id = os.getenv("WORKER_ID")
    if worker_id:
        boot_worker_threads(worker_id)
