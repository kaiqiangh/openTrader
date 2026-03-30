"""Rate limiting strategies for the API service.

Provides both in-memory (single-instance) and Redis-backed (multi-instance)
sliding window rate limiters with a common interface.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def is_allowed(self, key: str) -> tuple[bool, dict[str, object]]: ...


# ── In-Memory Rate Limiter ───────────────────────────────────────────────────


@dataclass
class InMemoryRateLimiter:
    """Sliding-window rate limiter using in-process deques.

    Single-instance only. For multi-instance deployments, use RedisRateLimiter.
    """

    window_seconds: int = 60
    max_requests: int = 300
    max_buckets: int = 10_000
    cleanup_interval: int = 1_000
    _windows: dict[str, deque[float]] = field(default_factory=dict)
    _request_count: int = field(default=0)

    async def is_allowed(self, key: str) -> tuple[bool, dict[str, object]]:
        now = time.time()
        self._request_count += 1

        # Periodic cleanup
        if self._request_count % self.cleanup_interval == 0:
            stale_cutoff = now - self.window_seconds * 2
            stale_keys = [k for k, v in self._windows.items() if not v or v[-1] < stale_cutoff]
            for k in stale_keys:
                del self._windows[k]

        # Bucket limit check
        if key not in self._windows and len(self._windows) >= self.max_buckets:
            return False, {"reason": "bucket_limit", "retry_after": self.window_seconds}

        bucket = self._windows.get(key)
        if bucket is None:
            bucket = deque()
            self._windows[key] = bucket

        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            retry_after = max(0, int(bucket[0] + self.window_seconds - now))
            return False, {"reason": "rate_limit", "retry_after": retry_after}

        bucket.append(now)
        return True, {"remaining": self.max_requests - len(bucket)}


# ── Redis-Backed Rate Limiter ────────────────────────────────────────────────


@dataclass
class RedisRateLimiter:
    """Sliding-window rate limiter using Redis sorted sets.

    Falls back to InMemoryRateLimiter if Redis is unreachable.
    """

    redis_url: str
    window_seconds: int = 60
    max_requests: int = 300
    _fallback: InMemoryRateLimiter | None = field(default=None, init=False)
    _redis_available: bool = field(default=True, init=False)

    async def is_allowed(self, key: str) -> tuple[bool, dict[str, object]]:
        if not self._redis_available:
            fallback = self._get_fallback()
            return await fallback.is_allowed(key)

        try:
            return await self._check_redis(key)
        except Exception:
            logger.warning("rate_limiter_redis_unavailable falling_back=in_memory")
            self._redis_available = False
            fallback = self._get_fallback()
            return await fallback.is_allowed(key)

    async def _check_redis(self, key: str) -> tuple[bool, dict[str, object]]:
        import asyncio

        now = time.time()
        window_start = now - self._window_seconds
        redis_key = f"ratelimit:{key}"

        def _sync_check() -> tuple[bool, dict[str, object]]:
            import redis as redis_lib

            client = redis_lib.from_url(self.redis_url, decode_responses=True)
            pipe = client.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {f"{now}": now})
            pipe.expire(redis_key, self._window_seconds * 2)
            results = pipe.execute()
            current_count = results[1]
            if current_count >= self._max_requests:
                return False, {"reason": "rate_limit", "retry_after": self._window_seconds}
            return True, {"remaining": self._max_requests - current_count - 1}

        return await asyncio.to_thread(_sync_check)

    def _get_fallback(self) -> InMemoryRateLimiter:
        if self._fallback is None:
            self._fallback = InMemoryRateLimiter(
                window_seconds=self.window_seconds,
                max_requests=self.max_requests,
            )
        return self._fallback
