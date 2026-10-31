import pytest

from profilecache import ProfileClient, TTLCache


class Clock:
    def __init__(self, now: float = 500.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_entry_alive_just_before_deadline():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    clock.advance(9.5)
    assert cache.get("a") == 1


def test_entry_expires_exactly_at_deadline():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    clock.advance(10)
    assert cache.get("a", "gone") == "gone"


def test_contains_is_false_exactly_at_deadline():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    clock.advance(10)
    assert "a" not in cache


def test_purge_removes_entry_exactly_at_deadline():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    cache.set("b", 2, ttl=20)
    clock.advance(10)
    assert cache.purge_expired() == 1
    assert cache.get("b") == 2


def test_read_does_not_extend_lifetime():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    clock.advance(6)
    assert cache.get("a") == 1
    clock.advance(4)
    assert cache.get("a", "gone") == "gone"


def test_repeated_reads_never_keep_entry_alive():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    for _ in range(4):
        clock.advance(2.5)
        cache.get("a")
    assert "a" not in cache


def test_write_refreshes_lifetime():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    clock.advance(8)
    cache.set("a", 2)
    clock.advance(8)
    assert cache.get("a") == 2
    clock.advance(2)
    assert cache.get("a", "gone") == "gone"


def test_write_can_shorten_lifetime():
    clock = Clock()
    cache = TTLCache(default_ttl=100, clock=clock)
    cache.set("a", 1)
    cache.set("a", 2, ttl=5)
    clock.advance(5)
    assert cache.get("a", "gone") == "gone"


def test_zero_ttl_write_is_rejected():
    cache = TTLCache(clock=Clock())
    with pytest.raises(ValueError):
        cache.set("a", 1, ttl=0)


def test_negative_ttl_write_is_rejected():
    cache = TTLCache(clock=Clock())
    with pytest.raises(ValueError):
        cache.set("a", 1, ttl=-3)


def test_nonpositive_default_ttl_is_rejected():
    with pytest.raises(ValueError):
        TTLCache(default_ttl=0, clock=Clock())
    with pytest.raises(ValueError):
        TTLCache(default_ttl=-1, clock=Clock())


def test_rejected_write_keeps_existing_entry():
    clock = Clock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    with pytest.raises(ValueError):
        cache.set("a", 2, ttl=0)
    assert cache.get("a") == 1


def test_rejected_write_does_not_store_new_key():
    cache = TTLCache(clock=Clock())
    with pytest.raises(ValueError):
        cache.set("a", 1, ttl=-1)
    assert "a" not in cache


def test_client_refetches_at_ttl_boundary():
    clock = Clock()
    calls = []

    def fetch(user_id):
        calls.append(user_id)
        return {"id": user_id, "n": len(calls)}

    client = ProfileClient(fetch, cache=TTLCache(clock=clock), ttl=30)
    client.get("u1")
    clock.advance(30)
    assert client.get("u1")["n"] == 2
    assert calls == ["u1", "u1"]


def test_client_sees_fresh_profile_despite_frequent_reads():
    clock = Clock()
    calls = []

    def fetch(user_id):
        calls.append(user_id)
        return {"id": user_id, "n": len(calls)}

    client = ProfileClient(fetch, cache=TTLCache(clock=clock), ttl=30)
    for _ in range(7):
        client.get("u1")
        clock.advance(10)
    assert len(calls) == 3


def test_client_update_restarts_lifetime():
    clock = Clock()
    client = ProfileClient(lambda uid: {"id": uid, "v": 1}, cache=TTLCache(clock=clock), ttl=30)
    client.get("u1")
    clock.advance(25)
    client.update("u1", {"id": "u1", "v": 2})
    clock.advance(25)
    assert client.get("u1")["v"] == 2
