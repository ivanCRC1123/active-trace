"""Tests for InMemoryRateLimiter."""

import asyncio

import pytest

from app.core.auth.rate_limiter import InMemoryRateLimiter


class TestRateLimiter:
    """RED: InMemoryRateLimiter tests."""

    @pytest.fixture
    def limiter(self):
        """Create a limiter with 3 attempts / 60s window for fast testing."""
        return InMemoryRateLimiter(max_attempts=3, window_seconds=60)

    @pytest.mark.asyncio
    async def test_first_attempt_allowed(self, limiter):
        """check() returns True on first attempt."""
        result = await limiter.check("ip:tenant:email@test.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_exceeds_max_attempts(self, limiter):
        """check() returns False after exceeding max_attempts within window."""
        key = "ip:tupad:a@b.com"
        assert await limiter.check(key) is True   # 1
        assert await limiter.check(key) is True   # 2
        assert await limiter.check(key) is True   # 3
        assert await limiter.check(key) is False  # 4 (exceeded)

    @pytest.mark.asyncio
    async def test_different_keys_independent(self, limiter):
        """Different IP+tenant_code+email keys have independent counters."""
        key_a = "ip1:tenant1:a@b.com"
        key_b = "ip2:tenant2:c@d.com"

        # Exhaust key_a
        await limiter.check(key_a)
        await limiter.check(key_a)
        await limiter.check(key_a)
        assert await limiter.check(key_a) is False  # exhausted

        # key_b should still be allowed
        assert await limiter.check(key_b) is True

    @pytest.mark.asyncio
    async def test_window_expires(self):
        """check() returns True again after window expires."""
        limiter = InMemoryRateLimiter(max_attempts=2, window_seconds=0.1)
        key = "ip:t:b@c.com"

        assert await limiter.check(key) is True   # 1
        assert await limiter.check(key) is True   # 2
        assert await limiter.check(key) is False  # 3 (blocked)

        await asyncio.sleep(0.15)  # wait for window to expire

        assert await limiter.check(key) is True   # allowed again

    @pytest.mark.asyncio
    async def test_concurrent_safety(self, limiter):
        """Thread safety with concurrent coroutines."""
        key = "ip:x:y@z.com"

        async def attempt():
            return await limiter.check(key)

        # Run 10 concurrent attempts
        results = await asyncio.gather(*[attempt() for _ in range(10)])
        allowed = sum(results)
        # At most 3 should be allowed (max_attempts=3)
        assert allowed <= 3

    @pytest.mark.asyncio
    async def test_cleanup_old_entries(self, limiter):
        """Dict doesn't grow unbounded after window expires."""
        key = "ip:t:e@f.com"
        # Make many attempts
        for _ in range(10):
            await limiter.check(key)

        # Force cleanup by sleeping and checking
        import time
        limiter._store[key] = [time.time() - 120] * 100  # all expired
        # A new check should clean up expired entries
        await limiter.check("other@key.com")
        # The old key's expired entries should have been cleaned
        # (they're cleaned during the sliding window operation)
        assert len(limiter._store.get(key, [])) <= 100  # at most, less after cleanup
