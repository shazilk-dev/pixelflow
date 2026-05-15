import os

import pytest
import redis


# Derive from REDIS_URL env var so this works inside Docker (redis://redis:6379/1)
# and locally (redis://localhost:6379/1). Always use DB 1 to isolate test state.
TEST_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").rsplit("/", 1)[0] + "/1"


@pytest.fixture(autouse=True)
def flush_test_db():
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield
    client.flushdb()
    client.close()
