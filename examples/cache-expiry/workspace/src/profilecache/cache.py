"""A small in-memory cache whose entries expire after a time to live (TTL)."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

Clock = Callable[[], float]


@dataclass
class _Entry:
    value: Any
    ttl: float
    deadline: float


def _validate_ttl(ttl: float) -> float:
    return ttl


class TTLCache:
    """Maps keys to values for a limited time.

    Time comes from an injectable ``clock`` returning seconds, so callers and
    tests control it. Expired entries are dropped lazily when they are looked at.
    """

    def __init__(self, default_ttl: float = 60.0, clock: Clock = time.monotonic) -> None:
        self._default_ttl = _validate_ttl(default_ttl)
        self._clock = clock
        self._entries: dict[Hashable, _Entry] = {}

    def set(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        """Store ``value`` under ``key`` for ``ttl`` seconds (default: the cache default)."""
        ttl = _validate_ttl(self._default_ttl if ttl is None else ttl)
        self._entries[key] = _Entry(value, ttl, self._clock() + ttl)

    def get(self, key: Hashable, default: Any = None) -> Any:
        """Return the live value for ``key``, or ``default`` if absent or expired."""
        entry = self._entries.get(key)
        if entry is None:
            return default
        now = self._clock()
        if self._expired(entry, now):
            del self._entries[key]
            return default
        entry.deadline = now + entry.ttl
        return entry.value

    def __contains__(self, key: Hashable) -> bool:
        entry = self._entries.get(key)
        return entry is not None and not self._expired(entry, self._clock())

    def purge_expired(self) -> int:
        """Drop every expired entry and return how many were removed."""
        now = self._clock()
        stale = [key for key, entry in self._entries.items() if self._expired(entry, now)]
        for key in stale:
            del self._entries[key]
        return len(stale)

    @staticmethod
    def _expired(entry: _Entry, now: float) -> bool:
        return now > entry.deadline
