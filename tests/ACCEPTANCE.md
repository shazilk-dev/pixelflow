# ACCEPTANCE.md — Acceptance Criteria & Test Specifications
## Distributed Image Processing Pipeline

> **Purpose:** Claude Code reads this file and writes failing tests BEFORE implementing
> each module. Tests pass only when the implementation is correct. This is the
> definition of "done" for every non-trivial piece of logic in this system.
>
> **How to use:**
> ```
> "Read @ACCEPTANCE.md Section {N}. Write all named test cases as failing pytest tests
> in tests/{filename}. Do not implement the module yet — only the tests."
> Then: "Now implement {module} until all tests in tests/{filename} pass."
> ```
>
> **What is NOT here:** UI component tests, boilerplate CRUD, standard HTTP status codes.
> Those are covered by TASKS.md VERIFY steps. This file covers logic that is
> non-obvious, has edge cases, or where a wrong implementation silently produces bad output.

---

## Section 1 — Image Transformations (`tests/test_image_tasks.py`)

The transformation pipeline is the core of the project. These tests verify
correctness of each PIL operation and the ordering/edge case rules.

**Test fixture:** Use a 1200×800 RGB JPEG test image (create programmatically with Pillow
`Image.new("RGB", (1200, 800), color=(100, 150, 200))`). This avoids depending on real files.

---

### AC-1.1 `test_resize_reduces_dimensions`
```
Given: A 1200×800 image
When:  "resize" transformation is applied
Then:  Output image dimensions are exactly 800×600
And:   Output file exists at the expected output path
And:   Output mode is still "RGB"
```

### AC-1.2 `test_resize_uses_lanczos`
```
Given: A 1200×800 image with a sharp diagonal line
When:  "resize" transformation is applied
Then:  Output quality is visually preserved (no nearest-neighbour pixelation)
Note:  Assert Image.LANCZOS was used by checking output pixel variance > threshold
       OR mock PIL.Image.resize and assert it was called with Image.LANCZOS
```

### AC-1.3 `test_grayscale_converts_mode`
```
Given: An RGB image (mode = "RGB")
When:  "grayscale" transformation is applied
Then:  Output image mode is "L"
And:   All pixels have equal R, G, B values when converted back to RGB
```

### AC-1.4 `test_blur_changes_pixel_values`
```
Given: An image with a sharp black-white edge (left half black, right half white)
When:  "blur" transformation is applied
Then:  Pixels near the edge are neither pure black (0) nor pure white (255)
And:   Output image dimensions are unchanged
And:   Output image mode is unchanged
```

### AC-1.5 `test_sharpen_increases_contrast`
```
Given: A uniform gray image with one slightly-off-gray pixel in the centre
When:  "sharpen" transformation is applied
Then:  The centre pixel deviates MORE from its neighbours than before sharpening
And:   Output image dimensions are unchanged
```

### AC-1.6 `test_watermark_adds_text`
```
Given: A plain white RGB image
When:  "watermark" transformation is applied
Then:  At least one pixel in the bottom-right quadrant is not pure white
       (confirms text was drawn — exact pixel values depend on font rendering)
And:   Output image mode is "RGB"
And:   Output image dimensions are unchanged
```

### AC-1.7 `test_transformation_order_is_canonical`
```
Given: An image and transformations ["watermark", "blur", "resize", "grayscale", "sharpen"]
       (deliberately wrong order — user selected them in random order)
When:  process_image applies the transformations
Then:  They are applied in canonical order: resize → grayscale → blur → sharpen → watermark
       (verify by mocking each PIL call and asserting call order)
```

### AC-1.8 `test_grayscale_plus_watermark_edge_case` ← CRITICAL
```
Given: An RGB image
When:  Both "grayscale" AND "watermark" are selected
Then:  No exception is raised (PIL cannot draw on mode "L")
And:   Output image mode is "RGB" (re-converted before watermark draw)
And:   Output image contains watermark text (verified by pixel check)
And:   Output image appears grayscale (R == G == B for non-watermark pixels)
```

### AC-1.9 `test_output_filename_convention`
```
Given: Input filename "sunset.jpg"
When:  Any transformation is applied
Then:  Output file is named "sunset_processed.jpg" (not "sunset.jpg" or "processed_sunset.jpg")
And:   Original file at input path is NOT modified
```

### AC-1.10 `test_single_transformation_each`
```
Given: A valid image
When:  Each transformation is applied in isolation (5 separate test cases)
Then:  Output file is created for each
And:   No exception is raised for any individual transformation
And:   Output file is a valid image (re-openable with PIL)
```

---

## Section 2 — Redis State Management (`tests/test_redis_state.py`)

These tests verify that the correct data is written to Redis at each stage.
Use a real Redis connection pointing to a test DB (`redis://localhost:6379/1`)
and flush it in `setup`/`teardown`.

---

### AC-2.1 `test_batch_meta_initial_state`
```
Given: A new batch is created with 5 images and ["resize", "grayscale"]
When:  create_batch() is called
Then:  Redis key "batch:{batch_id}:meta" exists
And:   Fields: status="QUEUED", total=5, completed=0, failed=0
And:   Fields: transformations='["resize", "grayscale"]'
And:   Field: created_at is a valid ISO 8601 string
And:   TTL of the key is between 86390 and 86400 seconds
```

### AC-2.2 `test_task_hash_initial_state`
```
Given: A task is dispatched for "sunset.jpg" in batch "batch-123"
When:  dispatch_tasks() creates the task record
Then:  Redis key "task:{task_id}" exists
And:   Fields: status="QUEUED", filename="sunset.jpg", batch_id="batch-123"
And:   Fields: worker_id="", duration_ms=0, output_size_kb=0, error=""
And:   task_id appears in "batch:{batch_id}:tasks" list
```

### AC-2.3 `test_task_status_transitions`
```
Given: A task exists in Redis with status="QUEUED"
When:  Worker picks up task → status update to "PROCESSING"
Then:  Redis task Hash shows status="PROCESSING", worker_id="{worker_id}", started_at set
When:  Worker completes task → status update to "SUCCESS"
Then:  Redis task Hash shows status="SUCCESS", duration_ms > 0, output_size_kb > 0
And:   completed_at is a valid ISO 8601 string
And:   batch:{batch_id}:meta "completed" field is incremented by 1
```

### AC-2.4 `test_batch_completed_counter_atomicity`
```
Given: A batch with total=3, and 3 tasks completing at near-simultaneous times
When:  Three workers each call HINCRBY on "batch:{batch_id}:meta" "completed"
Then:  Final value of "completed" is exactly 3 (no race condition, no double-count)
Note:  Test with threading.Thread — 3 threads each increment once; assert final = 3
```

### AC-2.5 `test_worker_heartbeat_sets_ttl`
```
Given: A worker with worker_id="worker_1"
When:  The heartbeat function runs
Then:  Redis key "worker:worker_1:status" exists
And:   TTL is between 25 and 30 seconds
And:   Fields: status, worker_id, last_heartbeat are all set
When:  No heartbeat for 31 seconds (simulated by setting TTL=1 and waiting)
Then:  Key no longer exists in Redis
```

### AC-2.6 `test_stream_event_push_and_pop`
```
Given: A batch_id "test-batch-abc"
When:  push_stream_event(batch_id, {"event": "task_update", "filename": "a.jpg"}) is called
Then:  LLEN "stream:test-batch-abc:events" == 1
When:  pop_stream_event(batch_id, timeout=1) is called
Then:  Returns the exact dict that was pushed
And:   LLEN "stream:test-batch-abc:events" == 0 (event was consumed)
```

### AC-2.7 `test_failed_task_increments_failed_counter`
```
Given: A task that raises an exception and exhausts all 3 retries
When:  Celery marks it as FAILED
Then:  Redis task Hash shows status="FAILED", error contains the exception message
And:   batch:{batch_id}:meta "failed" field is incremented by 1
And:   batch:{batch_id}:meta "completed" field is NOT incremented
```

---

## Section 3 — Batch Completion & Benchmark (`tests/test_benchmark.py`)

The batch_complete event calculation is the trickiest logic in the system.
A single worker computes it by reading all sibling task records from Redis.

---

### AC-3.1 `test_last_worker_detects_completion`
```
Given: A batch with total=3
And:   Tasks have duration_ms values: [1000, 1500, 2000]
When:  The third worker increments "completed" to 3 (equal to total)
Then:  That worker emits a "batch_complete" SSE event
And:   Workers 1 and 2 do NOT emit batch_complete (they incremented to 1 and 2)
```

### AC-3.2 `test_sequential_estimate_is_sum_of_durations`
```
Given: A completed batch with 4 tasks having duration_ms: [800, 1200, 950, 1050]
When:  The last worker calculates sequential_estimate_ms
Then:  sequential_estimate_ms == 4000 (exact sum of all task durations)
Note:  This simulates what would happen with 1 worker processing sequentially
```

### AC-3.3 `test_two_worker_estimate_is_half_of_sequential`
```
Given: sequential_estimate_ms = 4000
When:  two_worker_estimate_ms is calculated
Then:  two_worker_estimate_ms == 2000 (integer division acceptable)
```

### AC-3.4 `test_speedup_factor_calculation`
```
Given: sequential_estimate_ms = 12000, actual_ms = 4500
When:  speedup_factor is calculated
Then:  speedup_factor == round(12000 / 4500, 2) == 2.67
And:   speedup_factor is a float, not an int
```

### AC-3.5 `test_batch_complete_event_shape`
```
Given: A completed batch
When:  The batch_complete SSE event is constructed
Then:  It contains exactly these fields (no extras, no missing):
       event, batch_id, total, completed, failed,
       actual_ms, sequential_estimate_ms, speedup_factor
And:   All duration fields are integers (ms), not floats
And:   speedup_factor is a float rounded to 2 decimal places
Note:  Exact field names must match @DATA-MODEL.md Section 4.3
```

### AC-3.6 `test_partial_failure_batch_complete`
```
Given: A batch with total=5, where 1 task permanently FAILED after 3 retries
When:  The remaining 4 tasks complete
Then:  batch_complete is emitted when completed + failed == total
And:   completed=4, failed=1 in the event payload
And:   sequential_estimate_ms only sums the 4 successful task durations
       (failed task duration_ms is 0 — do not include in sum)
```

---

## Section 4 — API Validation (`tests/test_batch_api.py`)

Integration tests for the batch submission endpoint. Use FastAPI `TestClient`.

---

### AC-4.1 `test_valid_batch_returns_201`
```
Given: 3 valid JPEG files under 5MB and valid transformations
When:  POST /api/process-batch
Then:  Status 201
And:   Response body contains: batch_id (UUID format), total_images=3, status="QUEUED"
And:   Response body contains: created_at (ISO 8601)
```

### AC-4.2 `test_unsupported_file_format_returns_422`
```
Given: A .pdf file submitted as an image
When:  POST /api/process-batch
Then:  Status 422
And:   Response error message mentions "unsupported format" or "invalid file type"
And:   No Redis keys are created (batch was rejected before dispatch)
```

### AC-4.3 `test_oversized_file_returns_422`
```
Given: A valid JPEG that is 6MB (over the 5MB limit)
When:  POST /api/process-batch
Then:  Status 422
And:   Response error message mentions file size limit
And:   No Redis keys are created
```

### AC-4.4 `test_too_few_images_returns_422`
```
Given: Zero images submitted
When:  POST /api/process-batch
Then:  Status 422
```

### AC-4.5 `test_batch_status_response_shape`
```
Given: A submitted batch with known batch_id
When:  GET /api/batch/{batch_id}/status
Then:  Status 200
And:   Response contains exactly the fields defined in @DATA-MODEL.md Section 3.2 BatchStatusResponse
And:   All duration fields use "ms" suffix (elapsed_ms, duration_ms) — not "seconds"
And:   "tasks" array length equals number of submitted images
```

### AC-4.6 `test_unknown_batch_returns_404`
```
Given: A batch_id that does not exist in Redis
When:  GET /api/batch/nonexistent-id/status
Then:  Status 404
And:   Response body contains an informative error message
```

### AC-4.7 `test_invalid_transformation_key_returns_422`
```
Given: transformations=["thumbnail"] (removed from spec) or ["invalid_key"]
When:  POST /api/process-batch
Then:  Status 422
And:   Response message identifies the invalid transformation key
```

---

## Section 5 — Worker Control (`tests/test_worker_control.py`)

Tests for the pub/sub kill mechanism. These are unit tests — mock Redis pub/sub.

---

### AC-5.1 `test_kill_signal_targets_correct_worker`
```
Given: Three workers running with IDs "worker_1", "worker_2", "worker_3"
And:   All three subscribed to "channel:worker_control"
When:  API publishes {"action": "kill", "target": "worker_2"}
Then:  Only worker_2's listener thread processes the kill action
And:   worker_1 and worker_3 listeners ignore the message (target != their ID)
Note:  Mock os._exit; verify it's called exactly once, by worker_2's thread
```

### AC-5.2 `test_listener_runs_in_daemon_thread`
```
Given: Worker boot sequence runs boot_worker_threads(worker_id)
When:  Checking the created thread
Then:  thread.daemon == True
And:   thread.is_alive() == True after boot
```

### AC-5.3 `test_kill_endpoint_publishes_to_redis`
```
Given: POST /api/demo/kill-worker/worker_2 is called
When:  The endpoint handler runs
Then:  Redis PUBLISH was called on "channel:worker_control"
And:   The published message contains action="kill" and target="worker_2"
Note:  Use TestClient + mock redis_client.publish
```

---

## Section 6 — SSE Stream (`tests/test_stream.py`)

Test the SSE endpoint behaviour using FastAPI `TestClient` with a live Redis.

---

### AC-6.1 `test_sse_delivers_event_on_rpush`
```
Given: An open SSE connection to /api/stream/{batch_id}
When:  A task_update event is RPUSH'd to "stream:{batch_id}:events"
Then:  The SSE client receives the event within 1 second
And:   The received data parses as valid JSON
And:   The parsed JSON contains field "event"="task_update"
```

### AC-6.2 `test_sse_sends_keepalive_on_timeout`
```
Given: An open SSE connection with no events pushed for 16 seconds
When:  BLPOP times out
Then:  Client receives a keepalive SSE comment (": keepalive")
And:   Connection remains open after keepalive
```

### AC-6.3 `test_sse_closes_after_batch_complete`
```
Given: An open SSE connection
When:  A "batch_complete" event is pushed to the stream
Then:  The SSE generator yields the batch_complete event
And:   The generator exits (connection closes cleanly)
And:   No further events are yielded after batch_complete
```

---

## Section 7 — Acceptance Summary

| Section | Test File | Count | Covers |
|---------|-----------|-------|--------|
| 1 — Image Transformations | `test_image_tasks.py` | 10 | PIL operations, ordering, edge cases |
| 2 — Redis State | `test_redis_state.py` | 7 | All Redis key writes + TTL behaviour |
| 3 — Benchmark | `test_benchmark.py` | 6 | Completion detection, formula correctness |
| 4 — API Validation | `test_batch_api.py` | 7 | Request validation, response shapes |
| 5 — Worker Control | `test_worker_control.py` | 3 | Kill signal, daemon thread, pub/sub |
| 6 — SSE Stream | `test_stream.py` | 3 | Event delivery, keepalive, close |
| **Total** | | **36 named tests** | |

---

## Running All Tests

```bash
# From backend/ directory
pytest tests/ -v                              # all 36 tests
pytest tests/test_image_tasks.py -v          # Phase 1 only
pytest tests/ -k "test_grayscale" -v         # specific test
pytest tests/ --tb=short -q                  # quiet mode for CI

# Expected output when all pass:
# 36 passed in X.Xs
```

---

## Definition of Done

A feature is **done** when:
1. All acceptance tests for that section pass (`pytest` green)
2. The TASKS.md VERIFY step for that task passes (manual check)
3. `npm run type-check` passes (frontend changes)
4. No new `any` types introduced in TypeScript
5. No new `print()` statements in Python (use logger)

A phase is **done** when all of the above are true AND the phase GATE in TASKS.md passes.

---

*Write the tests first. If you can't write a test for it, you don't understand it well enough to build it.*
