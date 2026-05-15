"""
All Pydantic v2 request/response models.
Field names are canonical — defined here, never duplicated elsewhere.
REF: DATA-MODEL.md Section 3
"""
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ProcessBatchRequest(BaseModel):
    """
    Describes the multipart/form-data fields for POST /api/process-batch.
    `images` are received as List[UploadFile] via FastAPI File() — they are
    not included here because UploadFile is not a Pydantic-compatible type.
    Declare images as a separate File() parameter in the route handler.
    """
    model_config = ConfigDict()

    transformations: str    # JSON-encoded list e.g. '["resize","grayscale"]'
    num_workers: int        # 1 | 2 | 3 — UI hint only, actual count set by Docker


class KillWorkerRequest(BaseModel):
    model_config = ConfigDict()

    worker_id: str          # "worker_1" | "worker_2" | "worker_3"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class TaskSummary(BaseModel):
    model_config = ConfigDict()

    task_id: str
    filename: str
    status: str             # QUEUED | PROCESSING | SUCCESS | FAILED
    worker_id: str          # "" if not yet assigned
    duration_ms: int        # 0 if not complete
    error: str              # "" if no error


class WorkerSummary(BaseModel):
    model_config = ConfigDict()

    worker_id: str
    status: str             # IDLE | PROCESSING | OFFLINE
    current_filename: str   # "" if IDLE
    tasks_completed: int
    tasks_failed: int
    last_heartbeat: str     # ISO 8601; "" if OFFLINE


class BenchmarkData(BaseModel):
    model_config = ConfigDict()

    sequential_estimate_ms: int     # sum of all task duration_ms values
    two_worker_estimate_ms: int     # sequential_estimate_ms / 2
    actual_ms: int                  # batch completed_at - started_at
    speedup_factor: float           # sequential_estimate_ms / actual_ms


class ImageResult(BaseModel):
    model_config = ConfigDict()

    task_id: str
    filename: str
    status: str
    worker_id: str
    duration_ms: int
    original_size_kb: int
    output_size_kb: int             # 0 if FAILED
    original_url: str               # "/uploads/{batch_id}/{filename}"
    processed_url: str              # "/outputs/{batch_id}/{stem}_processed{ext}" | ""
    transformations_applied: list[str]


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------

class BatchCreatedResponse(BaseModel):
    model_config = ConfigDict()

    batch_id: str
    total_images: int
    status: str             # "QUEUED"
    created_at: str         # ISO 8601


class BatchStatusResponse(BaseModel):
    model_config = ConfigDict()

    batch_id: str
    status: str             # QUEUED | PROCESSING | COMPLETE | PARTIAL_FAILURE
    total: int
    completed: int
    failed: int
    elapsed_ms: int         # milliseconds since created_at — NOT seconds
    throughput: float       # completed / (elapsed_ms / 1000) images per second
    tasks: list[TaskSummary]


class WorkersStatusResponse(BaseModel):
    model_config = ConfigDict()

    workers: list[WorkerSummary]


class BatchResultsResponse(BaseModel):
    model_config = ConfigDict()

    batch_id: str
    status: str
    images: list[ImageResult]
    benchmark: BenchmarkData
