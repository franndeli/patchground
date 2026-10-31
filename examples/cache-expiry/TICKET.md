# Profiles stay stale, and bad TTLs are accepted silently

**Reported by:** support and on-call (two tickets merged)
**Component:** `profilecache`

## Symptom

1. Users who keep a dashboard open see an old display name for as long as the dashboard keeps
   polling. Profiles that nobody is looking at refresh fine. A profile cached with a 30 second
   lifetime but polled every 10 seconds was still served unchanged after several minutes.
2. In tests that drive the clock by hand, a profile cached for 30 seconds is still served at exactly
   30 seconds and only disappears a moment later. Operations tooling that expires entries on a
   schedule shows the same one-tick delay.
3. A deploy accidentally configured a cache lifetime of `0`. Nothing complained, and a negative value
   from a config typo was accepted the same way.

## Reproduction

```python
from profilecache import TTLCache

now = [0.0]
cache = TTLCache(default_ttl=10, clock=lambda: now[0])

cache.set("a", 1)
now[0] = 6
cache.get("a")           # a read at 6s
now[0] = 10
print(cache.get("a"))    # expected: None, actual: 1

cache.set("b", 2, ttl=0)  # accepted without error
```

## Expected

- An entry lives for exactly its TTL: at the instant the clock reaches its deadline it is expired.
  This applies to `get`, `in` and `purge_expired` alike.
- Writing a key starts its lifetime again with the TTL given for that write. Reading a key never
  changes how long it lives.
- A TTL of zero or less is invalid, both as the cache default and for an individual write. It must
  raise `ValueError`, and a rejected write must leave the cache exactly as it was.

## Notes

- Keep the injectable clock; do not sleep or use real time in tests.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- Add regression tests for the reported behavior and keep existing behavior intact.
- You may use your own editor and AI tools. The goal is to explain the cause and verify your fix,
  not merely make the reported cases pass.
