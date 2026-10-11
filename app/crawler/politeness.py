"""Per-domain politeness: one request at a time per domain, a minimum gap, Crawl-delay, adaptive slow-down (CR-F03, F05, F07).

The gate is per event loop (asyncio locks cannot be shared between loops). Time and sleeping go through `_now` / `_sleep`, so tests
can run with a fake clock.
"""

from __future__ import annotations

import asyncio
import random
import time
import weakref
from contextlib import asynccontextmanager

from app.crawler import config
from app.domains import domain_key


def _now() -> float:
    return time.monotonic()


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    """Exponential back-off with jitter: 1, 2, 4 ... seconds (CR-F04). `attempt` starts at 1 for the first retry.

    A server-supplied Retry-After is honoured when it is longer, up to config.RETRY_AFTER_MAX; the caller decides what to do beyond that.
    """
    delay = min(config.RETRY_BACKOFF_MAX, config.RETRY_BACKOFF * (2 ** max(0, attempt - 1)))
    delay *= 1 + random.uniform(-config.RETRY_JITTER, config.RETRY_JITTER)
    if retry_after is not None:
        delay = max(delay, retry_after)
    return max(0.0, delay)


class DomainGate:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._next_ok: dict[str, float] = {}
        self._crawl_delay: dict[str, float] = {}
        self._slowdown: dict[str, float] = {}
        self.requests: dict[str, int] = {}

    def interval(self, key: str) -> float:
        return max(config.DOMAIN_DELAY, self._crawl_delay.get(key, 0.0), self._slowdown.get(key, 0.0))

    def set_crawl_delay(self, key: str, seconds: float | None) -> None:
        if seconds and seconds > 0:
            self._crawl_delay[key] = min(float(seconds), config.CRAWL_DELAY_MAX)

    def slow_down(self, key: str) -> float:
        """A 403/429/5xx came back: double the gap (up to DOMAIN_DELAY_MAX). Returns the new gap."""
        current = self._slowdown.get(key, max(config.DOMAIN_DELAY, 0.5))
        self._slowdown[key] = min(config.DOMAIN_DELAY_MAX, current * 2)
        return self._slowdown[key]

    def delay_until(self, key: str, seconds_from_now: float) -> None:
        """Do not start another request to this domain before this moment (used for Retry-After)."""
        self._next_ok[key] = max(self._next_ok.get(key, 0.0), _now() + seconds_from_now)

    @asynccontextmanager
    async def slot(self, url_or_host: str):
        key = domain_key(url_or_host) or url_or_host
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            wait = self._next_ok.get(key, 0.0) - _now()
            if wait > 0:
                await _sleep(wait)
            try:
                yield key
            finally:
                self.requests[key] = self.requests.get(key, 0) + 1
                self._next_ok[key] = max(self._next_ok.get(key, 0.0), _now() + self.interval(key))


_GATES: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, DomainGate]" = weakref.WeakKeyDictionary()


def get_gate() -> DomainGate:
    loop = asyncio.get_running_loop()
    gate = _GATES.get(loop)
    if gate is None:
        gate = _GATES[loop] = DomainGate()
    return gate
