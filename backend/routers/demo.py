from fastapi import APIRouter

router = APIRouter()


@router.post("/demo/kill-worker/{worker_id}")
async def kill_worker(worker_id: str):
    """Stub — implemented in Phase 2 (T2.7)."""
    return {}
