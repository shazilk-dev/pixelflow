from fastapi import APIRouter

router = APIRouter()


@router.get("/workers/status")
async def get_workers_status():
    """Stub — implemented in Phase 2 (T2.3)."""
    return {}
