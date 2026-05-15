"""Phase 1 gate smoke test — run inside the API container."""
import os
import uuid

from PIL import Image

from core.redis_client import get_task, pop_stream_event, push_stream_event, set_task
from tasks.image_tasks import apply_transforms, build_output_path

batch_id = str(uuid.uuid4())
task_id = "smoke-task-1"
upload_dir = os.environ.get("UPLOAD_DIR", "/app/data/uploads")
output_dir = os.environ.get("OUTPUT_DIR", "/app/data/outputs")

os.makedirs(f"{upload_dir}/{batch_id}", exist_ok=True)
os.makedirs(f"{output_dir}/{batch_id}", exist_ok=True)

input_path = f"{upload_dir}/{batch_id}/test_image.jpg"
Image.new("RGB", (1200, 800), color=(100, 150, 200)).save(input_path)
print("Step 1: test image created at", input_path)

set_task(task_id, {
    "task_id": task_id,
    "batch_id": batch_id,
    "filename": "test_image.jpg",
    "status": "QUEUED",
    "worker_id": "",
    "duration_ms": 0,
    "output_size_kb": 0,
    "error": "",
})
task = get_task(task_id)
assert task["status"] == "QUEUED", "Expected QUEUED, got " + task["status"]
print("Step 2: task written to Redis, status=", task["status"])

output_path = build_output_path(input_path, f"{output_dir}/{batch_id}")
apply_transforms(input_path, output_path, ["resize", "grayscale", "watermark"])
assert os.path.exists(output_path), "Output file not created"
out = Image.open(output_path)
assert out.size == (800, 600), f"Expected (800,600), got {out.size}"
print("Step 3: transformations applied, output at", output_path, "size=", out.size)

push_stream_event(batch_id, {"event": "task_update", "task_id": task_id, "status": "SUCCESS"})
popped = pop_stream_event(batch_id, timeout=2)
assert popped is not None and popped["event"] == "task_update", f"Bad pop: {popped}"
print("Step 4: SSE push/pop OK:", popped)

print()
print("SMOKE TEST PASSED")
