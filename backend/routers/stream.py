from fastapi import APIRouter

router = APIRouter()


@router.get("/stream/{batch_id}")
async def stream_batch_events(batch_id: str):
    """Stub — implemented in Phase 2 (T2.5). Will return StreamingResponse."""
    return {}
