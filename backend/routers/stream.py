import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.redis_client import pop_stream_event

router = APIRouter()


@router.get("/stream/{batch_id}")
async def stream_batch_events(batch_id: str) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(batch_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _event_stream(batch_id: str):
    while True:
        result = await asyncio.to_thread(pop_stream_event, batch_id, 15)

        if result is None:
            yield ": keepalive\n\n"
            continue

        event_type = result.get("event", "message")
        yield f"event: {event_type}\ndata: {json.dumps(result)}\n\n"

        if event_type == "batch_complete":
            break
