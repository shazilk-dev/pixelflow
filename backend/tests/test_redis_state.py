"""
Tests for AC-2.1 through AC-2.7 — Redis State Management
Uses Redis DB 1 (redis://localhost:6379/1). DB is flushed before each test
by the autouse fixture in conftest.py.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

import pytest
import redis as redis_lib


TEST_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").rsplit("/", 1)[0] + "/1"


@pytest.fixture
def r():
    client = redis_lib.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Helpers — deferred imports so collection succeeds before implementation exists
# ---------------------------------------------------------------------------

def get_redis_client():
    """Return a redis_client pointing at test DB 1."""
    import importlib, sys  # noqa: E401
    # Patch settings so redis_client uses test DB
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("REDIS_URL", TEST_REDIS_URL)
        if "core.redis_client" in sys.modules:
            del sys.modules["core.redis_client"]
        if "core.config" in sys.modules:
            del sys.modules["core.config"]
        from core.redis_client import redis_client as rc  # noqa: PLC0415
    return rc


def get_job_service():
    import sys
    if "services.job_service" in sys.modules:
        del sys.modules["services.job_service"]
    from services import job_service  # noqa: PLC0415
    return job_service


def get_image_tasks():
    import sys
    if "tasks.image_tasks" in sys.modules:
        del sys.modules["tasks.image_tasks"]
    from tasks import image_tasks  # noqa: PLC0415
    return image_tasks


# ---------------------------------------------------------------------------
# AC-2.1  batch meta initial state
# ---------------------------------------------------------------------------

class TestBatchMetaInitialState:
    def test_batch_meta_initial_state(self, r):
        """
        AC-2.1: create_batch() writes correct initial Hash to Redis.
        Fields: status=QUEUED, total=5, completed=0, failed=0,
                transformations=JSON array, created_at=ISO8601, TTL≈86400s.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        from services.job_service import create_batch  # noqa: PLC0415

        batch_id, total = create_batch(
            filenames=["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"],
            transformations=["resize", "grayscale"],
            redis_url=TEST_REDIS_URL,
        )

        key = f"batch:{batch_id}:meta"
        assert r.exists(key), f"Key '{key}' must exist after create_batch()"

        meta = r.hgetall(key)
        assert meta["status"] == "QUEUED"
        assert int(meta["total"]) == 5
        assert int(meta["completed"]) == 0
        assert int(meta["failed"]) == 0
        assert json.loads(meta["transformations"]) == ["resize", "grayscale"]

        # created_at must parse as ISO 8601
        datetime.fromisoformat(meta["created_at"].replace("Z", "+00:00"))

        ttl = r.ttl(key)
        assert 86390 <= ttl <= 86400, f"TTL should be ~86400s, got {ttl}"


# ---------------------------------------------------------------------------
# AC-2.2  task hash initial state
# ---------------------------------------------------------------------------

class TestTaskHashInitialState:
    def test_task_hash_initial_state(self, r):
        """
        AC-2.2: dispatch_tasks() writes task Hash with correct fields and
        appends task_id to the batch task list.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        from services.job_service import dispatch_tasks  # noqa: PLC0415

        batch_id = "batch-123"
        task_ids = dispatch_tasks(
            batch_id=batch_id,
            filenames=["sunset.jpg"],
            transformations=["resize"],
            redis_url=TEST_REDIS_URL,
        )
        task_id = task_ids[0]

        task_key = f"task:{task_id}"
        assert r.exists(task_key), f"Key '{task_key}' must exist"

        task = r.hgetall(task_key)
        assert task["status"] == "QUEUED"
        assert task["filename"] == "sunset.jpg"
        assert task["batch_id"] == batch_id
        assert task["worker_id"] == ""
        assert int(task["duration_ms"]) == 0
        assert int(task["output_size_kb"]) == 0
        assert task["error"] == ""

        task_list = r.lrange(f"batch:{batch_id}:tasks", 0, -1)
        assert task_id in task_list, "task_id must appear in batch task list"


# ---------------------------------------------------------------------------
# AC-2.3  task status transitions
# ---------------------------------------------------------------------------

class TestTaskStatusTransitions:
    def test_task_status_transitions(self, r, tmp_path):
        """
        AC-2.3: Task progresses QUEUED → PROCESSING → SUCCESS with correct
        Redis field updates at each transition.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        from tasks.image_tasks import update_task_processing, update_task_success  # noqa: PLC0415

        # Seed initial task Hash (simulating what dispatch_tasks would write)
        task_id = "task-abc-001"
        batch_id = "batch-trans-001"
        r.hset(f"task:{task_id}", mapping={
            "task_id": task_id,
            "batch_id": batch_id,
            "filename": "photo.jpg",
            "status": "QUEUED",
            "worker_id": "",
            "duration_ms": 0,
            "output_size_kb": 0,
            "error": "",
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "started_at": "",
            "completed_at": "",
        })
        r.hset(f"batch:{batch_id}:meta", mapping={"total": 1, "completed": 0, "failed": 0})

        # Transition → PROCESSING
        update_task_processing(task_id, worker_id="worker_1", redis_url=TEST_REDIS_URL)

        task = r.hgetall(f"task:{task_id}")
        assert task["status"] == "PROCESSING"
        assert task["worker_id"] == "worker_1"
        assert task["started_at"] != "", "started_at must be set on PROCESSING"

        # Transition → SUCCESS
        output_path = str(tmp_path / "photo_processed.jpg")
        from PIL import Image
        Image.new("RGB", (10, 10)).save(output_path)

        update_task_success(
            task_id=task_id,
            batch_id=batch_id,
            output_path=output_path,
            duration_ms=1230,
            redis_url=TEST_REDIS_URL,
        )

        task = r.hgetall(f"task:{task_id}")
        assert task["status"] == "SUCCESS"
        assert int(task["duration_ms"]) > 0
        assert int(task["output_size_kb"]) > 0
        assert task["completed_at"] != "", "completed_at must be set on SUCCESS"
        datetime.fromisoformat(task["completed_at"].replace("Z", "+00:00"))

        completed = int(r.hget(f"batch:{batch_id}:meta", "completed"))
        assert completed == 1, "batch completed counter must be incremented on task SUCCESS"


# ---------------------------------------------------------------------------
# AC-2.4  batch completed counter atomicity
# ---------------------------------------------------------------------------

class TestBatchCompletedCounterAtomicity:
    def test_batch_completed_counter_atomicity(self, r):
        """
        AC-2.4: Three concurrent HINCRBY calls each increment 'completed' by 1.
        Final value must be exactly 3 — no race condition, no double-count.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        batch_id = "batch-atomic-001"
        r.hset(f"batch:{batch_id}:meta", mapping={"total": 3, "completed": 0, "failed": 0})

        rc = redis_lib.Redis.from_url(TEST_REDIS_URL, decode_responses=True)

        def increment():
            rc.hincrby(f"batch:{batch_id}:meta", "completed", 1)

        threads = [threading.Thread(target=increment) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rc.close()

        final = int(r.hget(f"batch:{batch_id}:meta", "completed"))
        assert final == 3, f"Expected 3 after 3 concurrent increments, got {final}"


# ---------------------------------------------------------------------------
# AC-2.5  worker heartbeat sets TTL
# ---------------------------------------------------------------------------

class TestWorkerHeartbeatSetsTTL:
    def test_worker_heartbeat_sets_ttl(self, r):
        """
        AC-2.5: Heartbeat writes worker Hash with TTL 25–30s.
        After TTL=1 expires, key is gone.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        from tasks.image_tasks import send_heartbeat  # noqa: PLC0415

        send_heartbeat(worker_id="worker_1", status="IDLE", redis_url=TEST_REDIS_URL)

        key = "worker:worker_1:status"
        assert r.exists(key), f"Key '{key}' must exist after heartbeat"

        ttl = r.ttl(key)
        assert 25 <= ttl <= 30, f"TTL should be 25–30s after heartbeat, got {ttl}"

        hw = r.hgetall(key)
        assert hw["status"] in ("IDLE", "PROCESSING")
        assert hw["worker_id"] == "worker_1"
        assert hw["last_heartbeat"] != ""

        # Simulate expiry: forcibly set TTL=1 and wait
        r.expire(key, 1)
        time.sleep(1.5)
        assert not r.exists(key), "Key must not exist after TTL expires"


# ---------------------------------------------------------------------------
# AC-2.6  stream event push and pop
# ---------------------------------------------------------------------------

class TestStreamEventPushAndPop:
    def test_stream_event_push_and_pop(self, r):
        """
        AC-2.6: push_stream_event → LLEN==1; pop_stream_event returns same dict → LLEN==0.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        from core.redis_client import push_stream_event, pop_stream_event  # noqa: PLC0415

        batch_id = "test-batch-abc"
        event = {"event": "task_update", "filename": "a.jpg"}

        push_stream_event(batch_id, event, redis_url=TEST_REDIS_URL)

        stream_key = f"stream:{batch_id}:events"
        assert r.llen(stream_key) == 1, "LLEN must be 1 after push"

        popped = pop_stream_event(batch_id, timeout=1, redis_url=TEST_REDIS_URL)
        assert popped == event, f"Popped event mismatch: {popped!r} != {event!r}"
        assert r.llen(stream_key) == 0, "LLEN must be 0 after pop (event consumed)"


# ---------------------------------------------------------------------------
# AC-2.7  failed task increments failed counter
# ---------------------------------------------------------------------------

class TestFailedTaskIncrementsFailedCounter:
    def test_failed_task_increments_failed_counter(self, r):
        """
        AC-2.7: Failed task increments 'failed' counter; 'completed' is NOT incremented;
        task Hash shows status=FAILED with error message.
        """
        import os
        os.environ["REDIS_URL"] = TEST_REDIS_URL

        from tasks.image_tasks import update_task_failed  # noqa: PLC0415

        task_id = "task-fail-001"
        batch_id = "batch-fail-001"

        r.hset(f"task:{task_id}", mapping={
            "task_id": task_id,
            "batch_id": batch_id,
            "filename": "broken.jpg",
            "status": "PROCESSING",
            "worker_id": "worker_1",
            "duration_ms": 0,
            "output_size_kb": 0,
            "error": "",
        })
        r.hset(f"batch:{batch_id}:meta", mapping={"total": 3, "completed": 0, "failed": 0})

        update_task_failed(
            task_id=task_id,
            batch_id=batch_id,
            error_message="PIL cannot open file: corrupt JPEG",
            redis_url=TEST_REDIS_URL,
        )

        task = r.hgetall(f"task:{task_id}")
        assert task["status"] == "FAILED"
        assert "PIL cannot open file" in task["error"]

        failed = int(r.hget(f"batch:{batch_id}:meta", "failed"))
        assert failed == 1, "failed counter must be incremented"

        completed = int(r.hget(f"batch:{batch_id}:meta", "completed"))
        assert completed == 0, "completed counter must NOT be incremented on failure"
