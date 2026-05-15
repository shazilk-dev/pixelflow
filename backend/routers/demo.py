import json

from fastapi import APIRouter

from core.redis_client import redis_client

router = APIRouter()

_VALID_WORKERS = frozenset({"worker_1", "worker_2", "worker_3"})


@router.post("/demo/kill-worker/{worker_id}")
async def kill_worker(worker_id: str) -> dict:
    if worker_id not in _VALID_WORKERS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown worker '{worker_id}'. Valid: {sorted(_VALID_WORKERS)}")

    redis_client.publish(
        "channel:worker_control",
        json.dumps({"action": "kill", "target": worker_id}),
    )
    return {"status": "kill signal sent", "target": worker_id}
