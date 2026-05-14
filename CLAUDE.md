# Distributed Image Processing Pipeline
> Full project spec: @PRD.md — read it before any task that touches architecture or requirements.

Uni project demonstrating DPC concepts: FastAPI (master) + Celery workers + Redis + Next.js dashboard.
Each Docker container = one distributed node. This framing is the entire point of the project.

---

## Commands

```bash
# Start everything
docker-compose up --build
docker-compose up --scale worker=5        # scale demo

# Backend dev (without Docker)
uvicorn main:app --reload --port 8000
celery -A celery_app worker --loglevel=info --concurrency=1 -n worker_1@%h

# Frontend dev
cd frontend && npm run dev                # port 3000
npm run type-check                        # run after every set of changes
npm run lint                              # run before every commit

# Tests — run single files, not the full suite
pytest tests/test_image_tasks.py -v
pytest tests/ -k "test_name" -v

# Redis debug
redis-cli keys "*"
redis-cli flushall                        # reset dev state
```

---

## CRITICAL — Non-Inferrable Rules

**These will not be obvious from reading the code. Do not change them.**

### 1. Celery config (`backend/celery_app.py`) — BOTH settings are required

```python
task_acks_late = True           # fault-tolerance demo: keeps task in queue until worker
                                # confirms completion. Without it: killed worker = lost task.

worker_prefetch_multiplier = 1  # load-balancing visual: forces 1 task at a time per worker.
                                # Without it: one worker grabs 4 tasks, others sit idle.
```

### 2. Shared Docker volume — ALL file I/O uses `/app/data/`

API and workers run in separate containers with isolated filesystems. They share one named
volume mounted at `/app/data/`.
- Uploads: `/app/data/uploads/{batch_id}/`
- Outputs: `/app/data/outputs/{batch_id}/`

NEVER use `./backend/uploads/` or any container-local path. Workers cannot read the API's filesystem.

### 3. Benchmark chart — compute from task durations, do NOT re-run the batch

```python
sequential_estimate = sum(t["duration"] for t in all_tasks)  # true 1-worker baseline
two_worker_estimate  = sequential_estimate / 2                # theoretical (label as "Estimated")
actual_time          = batch_end_ts - batch_start_ts          # measured 3-worker time
speedup_factor       = sequential_estimate / actual_time
```

### 4. Worker heartbeat — TTL 30s, refreshed every 2s

```python
redis_client.expire(f"worker:{worker_id}:status", 30)   # do not increase this value
```

Expired key = worker is OFFLINE on the dashboard. The TTL is the dead-man's switch.

---

## Redis Key Patterns (exact — no variations)

```
batch:{batch_id}:meta          Hash   {status, total, completed, created_at}
batch:{batch_id}:tasks         List   [task_id, ...]
task:{task_id}                 Hash   {filename, status, worker_id, duration}
worker:{worker_id}:status      Hash   {status, current_task, completed, heartbeat}  TTL:30s
stream:{batch_id}:events       List   ordered SSE event JSON
```

Status enums — use exactly these strings, nothing else:
- Task: `QUEUED` | `PROCESSING` | `SUCCESS` | `FAILED`
- Batch: `QUEUED` | `PROCESSING` | `COMPLETE` | `PARTIAL_FAILURE`
- Worker: `IDLE` | `PROCESSING` | `OFFLINE`

---

## SSE — Three Event Types (`useSSE.ts` must handle all three)

```
event: task_update      per-image status change
event: worker_status    worker state changed
event: batch_complete   all done → redirect to results page
```

Use native `EventSource` API. Do NOT use WebSockets — SSE is deliberate (one-way, HTTP-native, simpler).

---

## Code Style (only rules that differ from standard conventions)

**Python:**
- Pydantic v2 — `model_config = ConfigDict(...)` not `class Config`
- All FastAPI route handlers must be `async def`
- Worker ID format: `worker_1` / `worker_2` / `worker_3` (lowercase, underscore)

**TypeScript:**
- Next.js 15 App Router — server components by default; `"use client"` only when required
- `recharts` for all charts, `lucide-react` for all icons — do not add other libraries
- `any` and `// @ts-ignore` are banned — strict mode is on

**Both:**
- No `console.log` in committed code — use the structured logger
- No hardcoded URLs or Redis key strings outside their canonical definition files

---

## Absolute Constraints — Do Not Add

Even if they seem like improvements, these are explicitly out of scope (@PRD.md Section 3):

| What | Why it's banned |
|------|----------------|
| SQL database (SQLAlchemy, SQLite) | Redis-only is a deliberate design decision |
| WebSockets | SSE is chosen for simplicity — one-way push is all that's needed |
| OpenCV | Pillow is sufficient; OpenCV adds unnecessary complexity |
| User authentication | Out of scope for this project |
| Cloud storage (S3, Azure) | Shared Docker volume only |
| Celery `--concurrency` > 1 per container | Breaks "1 container = 1 distributed node" model |

---

## Git

```
# Branch naming convention
feature/backend-celery-setup
feature/frontend-dashboard
fix/shared-volume-path

# Commit message format  (type(scope): description)
feat(backend): add process_image task with PIL transformations
fix(docker): mount shared_data volume to all worker containers
feat(frontend): implement WorkerCard with pulse animation
```

Never commit: `.env`, `data/uploads/`, `data/outputs/` — add all three to `.gitignore`.

---

## Environment Variables

```bash
# backend/.env
REDIS_URL=redis://redis:6379/0
UPLOAD_DIR=/app/data/uploads
OUTPUT_DIR=/app/data/outputs
# WORKER_ID is NOT in .env — it's set per-container in docker-compose.yml

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

`WORKER_ID` must be declared individually per worker in `docker-compose.yml`.
Never use `os.getenv("WORKER_ID")` fallback or parse `--hostname` from sys.argv — fragile.

```yaml
worker_1:
  environment:
    - WORKER_ID=worker_1
worker_2:
  environment:
    - WORKER_ID=worker_2
worker_3:
  environment:
    - WORKER_ID=worker_3
```

---

## Demo Sequence (presentation order)

1. Upload 12 images → grayscale + resize + watermark → 3 workers → submit
2. Dashboard: 3 worker cards pulsing simultaneously → **parallelism**
3. Click "Kill Worker 2" mid-job → task reassigned to Worker 1 → **fault tolerance**
4. Results page: speedup chart + before/after gallery → **performance proof**
5. Terminal: `docker-compose up --scale worker=5` → **scalability**

### Kill Worker — Implementation Detail (IMPORTANT)

The "Kill Worker" button calls `POST /api/demo/kill-worker/{worker_id}`.
Label it `⚠️ Demo Only` in the UI.

DO NOT implement this by running `docker kill` from FastAPI. Containers are isolated —
FastAPI has no access to the Docker socket, and mounting it is a serious security anti-pattern.

**Correct implementation — Redis Pub/Sub:**

```python
# API endpoint (backend/routers/demo.py)
@app.post("/api/demo/kill-worker/{worker_id}")
async def kill_worker(worker_id: str):
    redis_client.publish("channel:worker_control", json.dumps({
        "action": "kill",
        "target": worker_id
    }))
    return {"status": "kill signal sent"}

# Each worker — control signal listener (backend/tasks/image_tasks.py)
def listen_for_control_signals(worker_id: str):
    pubsub = redis_client.pubsub()
    pubsub.subscribe("channel:worker_control")
    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            if data["action"] == "kill" and data["target"] == worker_id:
                os._exit(1)   # hard crash — simulates node failure

# IMPORTANT: start as a daemon thread on worker boot — NOT on the main thread.
# pubsub.listen() is a blocking loop. Calling it on the main thread freezes the
# worker permanently and it will never consume tasks from the queue.
import threading, os
# Worker ID comes from env — set per-container in docker-compose.yml.
# Do NOT parse --hostname from sys.argv or Celery internals. It's fragile.
worker_id = os.getenv("WORKER_ID")
if worker_id:
    threading.Thread(
        target=listen_for_control_signals,
        args=(worker_id,),
        daemon=True
    ).start()
```

This demonstrates Redis Pub/Sub as an additional DPC concept (broadcast messaging).
The `os._exit(1)` bypasses Python's graceful shutdown, simulating a real node crash so
Celery's `task_acks_late` kicks in and reassigns the task.

---

## Compaction

When compacting, always preserve:
- The active batch_id and list of files modified this session
- Any failing test names and their exact error messages
- Which docker-compose service was being debugged
