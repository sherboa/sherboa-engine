# Tests per-IP rolling 24-hour analysis quotas, expiration, Retry-After calculation, and concurrent quota enforcement.

import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from usage_limiter import (USAGE_LIMIT_MAX_ANALYSES, USAGE_LIMIT_WINDOW_SECONDS, UsageLimitExceeded, UsageLimiter)


@pytest.fixture
def limiter(tmp_path):
    """
    Use a separate temporary SQLite database for each test.
    """
    return UsageLimiter(str(tmp_path / "usage.db"))



def test_allows_twenty_analyses_for_one_ip(limiter):
    """
    An IP can start up to the configured analysis limit.
    """
    client_ip = "192.0.2.10"

    for _ in range(USAGE_LIMIT_MAX_ANALYSES):
        limiter.register_analysis(client_ip)



def test_rejects_twenty_first_analysis(limiter):
    """
    The next analysis is rejected once the quota is exhausted.
    """
    client_ip = "192.0.2.10"

    for _ in range(USAGE_LIMIT_MAX_ANALYSES):
        limiter.register_analysis(client_ip)

    with pytest.raises(UsageLimitExceeded) as exc_info:
        limiter.register_analysis(client_ip)

    assert exc_info.value.retry_after > 0



def test_each_ip_has_an_independent_quota(limiter):
    """
    Usage from one IP does not consume another IP's quota.
    """
    for _ in range(USAGE_LIMIT_MAX_ANALYSES):
        limiter.register_analysis("192.0.2.10")

    limiter.register_analysis("192.0.2.11")



def test_expired_records_do_not_count(limiter, monkeypatch):
    """
    An exhausted quota becomes available after the rolling window expires.
    """
    import usage_limiter

    now = 2_000_000_000.0
    monkeypatch.setattr(usage_limiter.time, "time", lambda: now)

    client_ip = "192.0.2.10"

    # Exhaust the quota while all records are inside the active window
    for _ in range(USAGE_LIMIT_MAX_ANALYSES):
        limiter.register_analysis(client_ip)

    with pytest.raises(UsageLimitExceeded):
        limiter.register_analysis(client_ip)

    # Move beyond the rolling window so all previous records expire
    monkeypatch.setattr(
        usage_limiter.time,
        "time",
        lambda: now + USAGE_LIMIT_WINDOW_SECONDS + 1,
    )

    # The IP should be allowed to start another analysis
    limiter.register_analysis(client_ip)



def test_retry_after_tracks_oldest_active_record(limiter, monkeypatch):
    """
    Retry-After reflects when the oldest active record expires.
    """
    import usage_limiter

    now = 2_000_000_000.0
    current_time = [now]
    monkeypatch.setattr(
        usage_limiter.time,
        "time",
        lambda: current_time[0],
    )

    client_ip = "192.0.2.10"

    for _ in range(USAGE_LIMIT_MAX_ANALYSES):
        limiter.register_analysis(client_ip)

    # Advance time slightly while all 20 records remain active
    current_time[0] = now + 10

    with pytest.raises(UsageLimitExceeded) as exc_info:
        limiter.register_analysis(client_ip)

    assert exc_info.value.retry_after == USAGE_LIMIT_WINDOW_SECONDS - 10



def test_concurrent_requests_cannot_exceed_quota(limiter):
    """
    Concurrent attempts cannot reserve more than the configured limit.
    """
    client_ip = "192.0.2.10"
    barrier = threading.Barrier(10)

    def attempt_analysis():
        barrier.wait()
        try:
            limiter.register_analysis(client_ip)
            return True
        except UsageLimitExceeded:
            return False

    # Ten simultaneous attempts should all fit within the remaining quota
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: attempt_analysis(), range(10)))

    assert sum(results) == 10

    # Ten more simultaneous attempts fill the quota to 20
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: attempt_analysis(), range(10)))

    assert sum(results) == 10

    # Any further attempt must be rejected
    with pytest.raises(UsageLimitExceeded):
        limiter.register_analysis(client_ip)
