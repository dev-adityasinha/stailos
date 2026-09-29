"""In-memory sliding-window rate limiter for sensitive endpoints (auth).

Single-process MVP implementation; the `RateLimiter` interface maps 1:1 onto a
Redis INCR/EXPIRE implementation for multi-instance deployments.
"""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import RateLimitError

_hits: dict[str, deque[float]] = defaultdict(deque)

AUTH_LIMIT = 20          # requests
AUTH_WINDOW_SECONDS = 60


def check_rate_limit(request: Request, bucket: str, limit: int = AUTH_LIMIT,
                     window: int = AUTH_WINDOW_SECONDS) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{ip}"
    now = time.monotonic()
    q = _hits[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        raise RateLimitError("Too many requests; slow down and try again shortly.")
    q.append(now)
