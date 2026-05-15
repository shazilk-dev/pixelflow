from fastapi import APIRouter

router = APIRouter()


@router.post("/process-batch", status_code=201)
async def process_batch():
    """Stub — implemented in Phase 2 (T2.1, T2.2)."""
    return {}


@router.get("/batch/{batch_id}/status")
async def get_batch_status(batch_id: str):
    """Stub — implemented in Phase 2 (T2.2)."""
    return {}


@router.get("/batch/{batch_id}/results")
async def get_batch_results(batch_id: str):
    """Stub — implemented in Phase 2 (T2.2)."""
    return {}
