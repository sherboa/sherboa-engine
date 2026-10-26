# This module defines shared pytest fixtures for API tests, including an isolated FastAPI test client, a temporary usage database, and rate limiter state cleanup.

import os
import tempfile
import pytest
from fastapi.testclient import TestClient
import rate_limiter

os.environ["SHERBOA_USAGE_DB_PATH"] = os.path.join(
    tempfile.gettempdir(),
    "sherboa-usage-test.db",
)


@pytest.fixture
def client(tmp_path):
    """
    Provide an isolated API client and temporary usage database.
    """

    import main

    # Save the original limiter so it can be restored after the test
    original_limiter = main.usage_limiter
    
    # Use a dedicated SQLite database for this test
    main.usage_limiter = main.UsageLimiter(tmp_path / "usage.db")

    # Reset the in-memory short-window limiter state
    with rate_limiter.rate_limit_lock:
        rate_limiter.request_timestamps.clear()
        rate_limiter.analysis_timestamps.clear()
        rate_limiter.last_rate_limit_cleanup = 0.0

    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.usage_limiter = original_limiter

        with rate_limiter.rate_limit_lock:
            rate_limiter.request_timestamps.clear()
            rate_limiter.analysis_timestamps.clear()
            rate_limiter.last_rate_limit_cleanup = 0.0
