"""Profile client that avoids refetching recently loaded profiles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from profilecache.cache import TTLCache

Profile = dict[str, Any]

_MISSING = object()


class ProfileClient:
    """Loads profiles through ``fetch`` and keeps them in a cache for ``ttl`` seconds."""

    def __init__(
        self,
        fetch: Callable[[str], Profile],
        cache: TTLCache | None = None,
        ttl: float = 30.0,
    ) -> None:
        self._fetch = fetch
        self._cache = cache if cache is not None else TTLCache()
        self._ttl = ttl

    def get(self, user_id: str) -> Profile:
        cached = self._cache.get(user_id, _MISSING)
        if cached is not _MISSING:
            return cached
        profile = self._fetch(user_id)
        self._cache.set(user_id, profile, ttl=self._ttl)
        return profile

    def update(self, user_id: str, profile: Profile) -> None:
        """Replace the cached profile after the user edited it."""
        self._cache.set(user_id, profile, ttl=self._ttl)
