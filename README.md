# Distributed Image Processing Pipeline

A full-stack distributed system that breaks a batch of images into parallel tasks, dispatches them across Celery worker nodes via a Redis message queue, and streams real-time progress to a Next.js dashboard. Demonstrates master-worker architecture, inter-process communication, parallel execution, fault tolerance, load balancing, broadcast messaging (Pub/Sub), and Amdahl's Law — all inside Docker containers on a single machine.

---

## Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) — Compose v2 required (`docker compose version`)
- Node.js 20+ *(local frontend dev only — not needed for Docker)*
- Python 3.12+ *(local backend dev only — not needed for Docker)*

---

## Quick Start

```bash
git clone <repo> && cd distributed-image-pipeline
cp .env.example .env
docker compose up --build
# open http://localhost:3000
```

---

## Demo Script

**Step 1 — Upload a batch**
Open http://localhost:3000. Upload 6–12 images (JPG / PNG / WebP, max 5 MB each). Select **Resize + Grayscale + Watermark**. Set workers to **3**. Click **Process Images**.

**Step 2 — Watch parallelism**
The dashboard shows three worker cards pulsing green simultaneously — each processing a different image. The activity feed scrolls as tasks complete. The throughput counter shows images/sec in real time.

**Step 3 — Demonstrate fault tolerance**
While the batch is running, click **⚠️ Kill worker_2**. Worker 2 goes OFFLINE. Its in-progress task is automatically reassigned to a surviving worker via Celery's `task_acks_late`. The batch completes with all images processed.

**Step 4 — Review results**
The dashboard auto-redirects to the results page: a speedup chart (Amdahl's Law empirically) and a before/after gallery for every processed image.

**Step 5 — Scale horizontally**
```bash
docker compose --profile scaling up --scale worker=5
```
Five additional Celery workers join the queue with zero code changes.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HOST MACHINE                                                           │
│                                                                         │
│  ┌──────────────────┐        HTTP/SSE         ┌──────────────────────┐ │
│  │   FRONTEND       │ ◄────────────────────── │   API (Master Node)  │ │
│  │   Next.js :3000  │ ──── POST /process ───► │   FastAPI :8000      │ │
│  └──────────────────┘                         └──────────┬───────────┘ │
│                                                          │             │
│                                              PUBLISH/SUBSCRIBE         │
│                                              + CELERY BROKER           │
│                                                          │             │
│                                               ┌──────────▼───────────┐ │
│                                               │   REDIS :6379         │ │
│                                               │   broker + state +    │ │
│                                               │   pub/sub + results   │ │
│                                               └──┬───────┬────────┬──┘ │
│                                                  │       │        │    │
│                              ┌───────────────────┘       │        └──────────────────┐
│                              ▼                           ▼                           ▼ │
│                    ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐ │
│                    │   WORKER 1       │   │   WORKER 2       │   │   WORKER 3       │ │
│                    │   Celery+Pillow  │   │   Celery+Pillow  │   │   Celery+Pillow  │ │
│                    └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘ │
│                             │                      │                      │           │
│                    ┌────────▼──────────────────────▼──────────────────────▼─────────┐ │
│                    │              SHARED DOCKER VOLUME: /app/data/                  │ │
│                    │        uploads/{batch_id}/        outputs/{batch_id}/          │ │
│                    └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS, Recharts |
| API / Master Node | FastAPI, Python 3.12, Pydantic v2, Uvicorn |
| Task Queue | Celery 5.4, Redis 7 |
| Image Processing | Pillow 11 |
| Real-time transport | Server-Sent Events (SSE), native `EventSource` API |
| Infrastructure | Docker Compose, named volumes |

---

## DPC Concepts Demonstrated

| Concept | Where It's Demonstrated |
|---|---|
| **Master-Worker Architecture** | FastAPI (master) dispatches tasks; Celery workers execute them |
| **Message Passing (IPC)** | Tasks travel through Redis queue from master to workers — inter-process communication |
| **Parallel Processing** | 3 workers process 3 different images simultaneously — true parallelism |
| **Task Scheduling** | Celery's FIFO queue schedules tasks; workers pull greedily (self-scheduling) |
| **Load Balancing** | Redis queue distributes tasks evenly — a free worker immediately pulls the next task |
| **Fault Tolerance** | Kill a worker → Celery detects loss → re-queues task → another worker picks it up |
| **Task Retry** | `max_retries=3` — failed tasks retry automatically with exponential backoff |
| **Scalability** | `docker compose --profile scaling up --scale worker=5` adds workers without code changes |
| **Performance Benchmarking** | Speedup chart shows empirical speedup factor; Amdahl's Law explains the ceiling |
| **Distributed State** | Redis stores shared state (task status, worker heartbeats) accessible by all nodes |
| **Broadcast Messaging (Pub/Sub)** | Kill-worker signal uses Redis Pub/Sub — API publishes to `channel:worker_control`, all workers subscribe |

> **Hardware note:** Image processing is CPU-bound. Set worker count ≤ physical CPU cores for best results. On a 4-core laptop, 3 workers is the sweet spot.
