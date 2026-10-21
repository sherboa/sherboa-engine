# This module provides request rate limiting and concurrency control for the sherboa API.
# It enforces per-IP request limits, applies stricter limits to video analysis requests, periodically cleans up inactive client records, and prevents concurrent video analyses within the same application process.

import threading
import time
from collections import defaultdict, deque
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

########################################################################################################################
# CONSTANTS
########################################################################################################################
RATE_LIMIT_WINDOW_SECONDS = 60  # Duration of the rolling rate-limit window
RATE_LIMIT_MAX_REQUESTS = 30  # Maximum general requests allowed per IP within the window
RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = 60  # How often expired client records are removed
RATE_LIMIT_MAX_TRACKED_IPS = 5000  # Maximum number of client IPs tracked in the general rate limiter
RATE_LIMIT_MAX_ANALYSES = 5  # Maximum /vmaf requests allowed per IP within the same window


########################################################################################################################
# SHARED STATE AND LOCKS
########################################################################################################################
rate_limit_lock = threading.Lock()  # Protects shared rate-limit dictionaries from concurrent access by request handlers
request_timestamps = defaultdict(deque)  # Maps each client IP to its recent general request timestamps; a deque allows expired timestamps to be removed efficiently from the oldest end
analysis_timestamps = {}  # Maps each client IP to its recent /vmaf request timestamps
last_rate_limit_cleanup = 0.0  # Monotonic time of the last cleanup; unaffected by system clock adjustments
analysis_lock = threading.Lock()  # Allows only one video analysis at a time within this application process


########################################################################################################################
# ANALYSIS CONCURRENCY CONTROL
########################################################################################################################
def limit_analysis_concurrency():
    """
    Prevent multiple video analyses from running simultaneously in this process.

    Returns HTTP 429 when another analysis is already running.
    The lock is always released when the endpoint finishes or raises an exception.
    """

    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="an analysis is already in progress, please try again later."
        )

    try:
        yield
    finally:
        analysis_lock.release()


########################################################################################################################
# REQUEST RATE LIMITING
########################################################################################################################
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        """
        Apply per-IP request limits before passing the request to the endpoint.

        Uvicorn must be configured to trust forwarded headers only from the
        authorized reverse proxy. Otherwise, request.client.host may identify
        the proxy rather than the actual visitor.

        The general limit applies to all paths. Requests to /vmaf are also
        subject to the stricter analysis-specific limit.
        """
        # Use the client IP identified by Uvicorn, not an untrusted header
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        global last_rate_limit_cleanup

        with rate_limit_lock:
            # Periodically remove inactive IPs instead of scanning on every request
            if now - last_rate_limit_cleanup >= RATE_LIMIT_CLEANUP_INTERVAL_SECONDS:
                inactive_ips = [
                    ip for ip, entries in request_timestamps.items()
                    if not entries or now - entries[-1] >= RATE_LIMIT_WINDOW_SECONDS
                ]

                for ip in inactive_ips:
                    del request_timestamps[ip]

                inactive_analysis_ips = [  # Clean up the analysis-specific records in the same periodic pass; this avoids scanning the entire analysis dictionary on every request
                    ip
                    for ip, entries in analysis_timestamps.items()
                    if not entries
                    or now - entries[-1] >= RATE_LIMIT_WINDOW_SECONDS
                ]

                for ip in inactive_analysis_ips:
                    del analysis_timestamps[ip]

                last_rate_limit_cleanup = now

            timestamps = request_timestamps.get(client_ip)   # Retrieve the existing request history for this client

            # Bound memory usage by refusing to track additional IPs when capacity is full; existing clients can continue using their already allocated records
            if timestamps is None:
                if len(request_timestamps) >= RATE_LIMIT_MAX_TRACKED_IPS:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=429,
                        content={"detail": "rate limit capacity reached, please try again later."},
                        headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
                    )

                timestamps = deque()
                request_timestamps[client_ip] = timestamps

            # Remove requests outside the active time window
            while timestamps and now - timestamps[0] >= RATE_LIMIT_WINDOW_SECONDS:
                timestamps.popleft()


            if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:  # Reject requests that exceed the general per-IP limit
                from fastapi.responses import JSONResponse

                retry_after = max(   # Return the time remaining until the oldest request expires
                    1,
                    int(RATE_LIMIT_WINDOW_SECONDS - (now - timestamps[0]) + 0.999),
                )

                return JSONResponse(
                    status_code=429,
                    content={"detail": "too many requests, please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)  # Count this request against the general limit; a request rejected by the analysis-specific limit still counts here

            # Apply a stricter limit to the resource-intensive video analysis endpoint
            if request.url.path == "/vmaf":
                analyses = analysis_timestamps.get(client_ip)

                if analyses is None:
                    analyses = deque()
                    analysis_timestamps[client_ip] = analyses

                while analyses and now - analyses[0] >= RATE_LIMIT_WINDOW_SECONDS:  # Remove analysis attempts that have expired from the rolling window
                    analyses.popleft()

                if len(analyses) >= RATE_LIMIT_MAX_ANALYSES:  # Reject requests that exceed the analysis-specific per-IP limit
                    retry_after = max(
                        1,
                        int(
                            RATE_LIMIT_WINDOW_SECONDS
                            - (now - analyses[0])
                            + 0.999
                        ),
                    )

                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": "analysis rate limit reached, please try again later."
                        },
                        headers={"Retry-After": str(retry_after)},
                    )

                analyses.append(now)  # Count the attempt before endpoint processing begins; this also limits repeated invalid or unsuccessful analysis requests

        return await call_next(request)  # Continue to routing, multipart processing, dependencies, and the endpoint
