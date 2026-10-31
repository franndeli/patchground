from profilecache import ProfileClient, TTLCache


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_get_returns_stored_value():
    cache = TTLCache(default_ttl=10, clock=FakeClock())
    cache.set("a", 1)
    assert cache.get("a") == 1


def test_missing_key_returns_default():
    cache = TTLCache(default_ttl=10, clock=FakeClock())
    assert cache.get("nope") is None
    assert cache.get("nope", "fallback") == "fallback"


def test_entry_is_gone_well_after_deadline():
    clock = FakeClock()
    cache = TTLCache(default_ttl=10, clock=clock)
    cache.set("a", 1)
    clock.advance(60)
    assert cache.get("a") is None
    assert "a" not in cache


def test_per_write_ttl_overrides_default():
    clock = FakeClock()
    cache = TTLCache(default_ttl=100, clock=clock)
    cache.set("short", 1, ttl=5)
    clock.advance(20)
    assert cache.get("short") is None


def test_client_fetches_once_while_fresh():
    clock = FakeClock()
    calls = []

    def fetch(user_id):
        calls.append(user_id)
        return {"id": user_id}

    client = ProfileClient(fetch, cache=TTLCache(clock=clock), ttl=30)
    assert client.get("u1") == {"id": "u1"}
    clock.advance(5)
    assert client.get("u1") == {"id": "u1"}
    assert calls == ["u1"]
