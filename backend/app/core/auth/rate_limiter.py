"""In-memory sliding-window rate limiter for auth endpoints.

Thread-safe via asyncio.Lock. Not suitable for multi-process deployments.
"""

import time
from collections import defaultdict
from threading import Lock

from app.core.config import settings


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by f"{ip}:{tenant_code}:{email}"."""

    def __init__(
        self,
        max_attempts: int | None = None,
        window_seconds: int | None = None,
    ):
        self._max_attempts = max_attempts or settings.RATE_LIMIT_MAX_ATTEMPTS
        self._window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self._store: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    async def check(self, key: str) -> bool:
        """Record attempt and return True if allowed, False if rate-limited.

        Sliding window: only attempts within the last window_seconds count.
        """
        now = time.time()
        cutoff = now - self._window_seconds

        with self._lock:
            # Prune expired timestamps (sliding window)
            timestamps = self._store[key]
            self._store[key] = [t for t in timestamps if t > cutoff]

            if len(self._store[key]) >= self._max_attempts:
                return False

            self._store[key].append(now)
            return True

    def _cleanup(self):
        """Remove stale entries (optional maintenance)."""
        now = time.time()
        cutoff = now - self._window_seconds
        with self._lock:
            stale = [k for k, v in self._store.items() if all(t < cutoff for t in v)]
            for k in stale:
                del self._store[k]


# Module-level singleton
rate_limiter = InMemoryRateLimiter()
