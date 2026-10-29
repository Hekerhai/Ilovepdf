"""Fixed-window rate limiting for sensitive endpoints (sign-in, magic links, job creation)."""

import time
from collections import defaultdict

from app.domain.errors import QuotaExceeded


class MemoryRateLimiter:
    """Per-process limiter; fine for one API replica and for tests."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        hits = [t for t in self._hits[key] if now - t < window_seconds]
        if len(hits) >= limit:
            raise QuotaExceeded("Too many attempts. Please wait a moment and try again.", code="rate_limited")
        hits.append(now)
        self._hits[key] = hits


class RedisRateLimiter:
    """Shared across API replicas."""

    def __init__(self, redis_url: str):
        from redis import Redis

        self._redis = Redis.from_url(redis_url)

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        bucket = f"rl:{key}:{int(time.time() // window_seconds)}"
        pipe = self._redis.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, window_seconds)
        count, _ = pipe.execute()
        if count > limit:
            raise QuotaExceeded("Too many attempts. Please wait a moment and try again.", code="rate_limited")
