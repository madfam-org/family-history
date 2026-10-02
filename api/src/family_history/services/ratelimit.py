"""A small in-process sliding-window rate limiter keyed by a hashed client address.

It protects the public waitlist from bursts. It is per process (one API pod in M1); a
multi-replica deployment would need a shared store.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            self._hits.move_to_end(key)
            while hits and hits[0] <= cutoff:
                hits.popleft()
            allowed = len(hits) < self._limit
            if allowed:
                hits.append(now)
            while len(self._hits) > self._max_keys:
                self._hits.popitem(last=False)
            return allowed


class AddressHasher:
    """Salted SHA-256 of a client address.

    The salt is random per process, so a stored hash cannot be reversed by brute-forcing the
    IPv4 space and cannot be linked across restarts. It is enough for rate limiting and for
    spotting bursts in one process's lifetime.
    """

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt or secrets.token_bytes(32)

    def __call__(self, address: str) -> str:
        return hashlib.sha256(self._salt + address.encode("utf-8")).hexdigest()
