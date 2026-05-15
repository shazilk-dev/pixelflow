import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.schemas import BatchCreatedResponse, BatchResultsResponse, BatchStatusResponse
from services.job_service import (
    create_batch,
    dispatch_tasks,
    get_batch_results,
    get_batch_status,
)

router = APIRouter()

_VALID_TRANSFORMATIONS = frozenset({"resize", "grayscale", "blur", "sharpen", "watermark"})


def _parse_transformations(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="transformations must be a valid JSON array string.")

    if not isinstance(parsed, list):
        raise HTTPException(status_code=422, detail="transformations must be a JSON array.")

    invalid = [t for t in parsed if t not in _VALID_TRANSFORMATIONS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transformation key(s): {invalid}. "
                   f"Accepted: {sorted(_VALID_TRANSFORMATIONS)}.",
        )

    return parsed


@router.post("/process-batch", status_code=201, response_model=BatchCreatedResponse)
async def process_batch(
    images: list[UploadFile] = File(...),
    transformations: str = Form(...),
    num_workers: int = Form(default=3),
) -> BatchCreatedResponse:
    if not images:
        raise HTTPException(status_code=422, detail="At least one image is required.")

    transforms = _parse_transformations(transformations)

    result = await create_batch(images, transforms)
    dispatch_tasks(result["batch_id"], result["filenames"], transforms)

    return BatchCreatedResponse(
        batch_id=result["batch_id"],
        total_images=result["total_images"],
        status="QUEUED",
        created_at=_get_created_at(result["batch_id"]),
    )


def _get_created_at(batch_id: str) -> str:
    from core.redis_client import redis_client
    return redis_client.hget(f"batch:{batch_id}:meta", "created_at") or ""


@router.get("/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status_route(batch_id: str) -> BatchStatusResponse:
    return get_batch_status(batch_id)


@router.get("/batch/{batch_id}/results", response_model=BatchResultsResponse)
async def get_batch_results_route(batch_id: str) -> BatchResultsResponse:
    return get_batch_results(batch_id)
