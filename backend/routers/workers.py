from fastapi import APIRouter

from core.redis_client import get_all_worker_statuses
from models.schemas import WorkerSummary, WorkersStatusResponse

router = APIRouter()


@router.get("/workers/status", response_model=WorkersStatusResponse)
async def get_workers_status() -> WorkersStatusResponse:
    raw = get_all_worker_statuses()
    workers = [
        WorkerSummary(
            worker_id=w.get("worker_id", ""),
            status=w.get("status", "OFFLINE"),
            current_filename=w.get("current_filename", ""),
            tasks_completed=int(w.get("tasks_completed", 0)),
            tasks_failed=int(w.get("tasks_failed", 0)),
            last_heartbeat=w.get("last_heartbeat", ""),
        )
        for w in raw
    ]
    return WorkersStatusResponse(workers=workers)
