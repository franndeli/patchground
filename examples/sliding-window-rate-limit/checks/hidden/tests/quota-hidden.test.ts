import { test, expect } from "vitest";
import { SlidingWindowRateLimiter } from "../src/rate-limiter.js";

test("rolling oracle agrees across interleaved clients and cleanup", () => {
  let now = 1000;
  const capacity = 3;
  const windowMs = 17;
  const limiter = new SlidingWindowRateLimiter({ capacity, windowMs, clock: () => now });
  const history = new Map<string, number[]>();
  const clients = ["__proto__", "alpha", "", "constructor"];
  for (let i = 0; i < 120; i += 1) {
    now += i % 5;
    if (i % 7 === 0) {
      let removed = 0;
      for (const [id, events] of history) {
        const live = events.filter(time => time > now - windowMs);
        if (live.length === 0) { history.delete(id); removed += 1; }
        else history.set(id, live);
      }
      expect(limiter.cleanup()).toBe(removed);
    }
    const client = clients[i % clients.length] ?? "";
    const live = (history.get(client) ?? []).filter(time => time > now - windowMs);
    const allowed = live.length < capacity;
    if (allowed) live.push(now);
    history.set(client, live);
    expect(limiter.check(client)).toEqual({ allowed, remaining: capacity - live.length });
  }
});

test("one millisecond window separates distinct same-time admissions", () => {
  let now = 42;
  const limiter = new SlidingWindowRateLimiter({ capacity: 3, windowMs: 1, clock: () => now });
  expect([limiter.check("x"), limiter.check("x"), limiter.check("x")].map(d => d.remaining)).toEqual([2, 1, 0]);
  expect(limiter.check("x").allowed).toBe(false);
  now = 43;
  expect(limiter.check("x")).toEqual({ allowed: true, remaining: 2 });
});

test("frequent rejection cannot shift the next admission deadline", () => {
  let now = 0;
  const limiter = new SlidingWindowRateLimiter({ capacity: 1, windowMs: 30, clock: () => now });
  limiter.check("x");
  for (now = 1; now < 30; now += 1) expect(limiter.check("x").allowed).toBe(false);
  expect(limiter.check("x")).toEqual({ allowed: true, remaining: 0 });
});

test("cleanup prunes partial history and later retires every idle key", () => {
  let now = 0;
  const limiter = new SlidingWindowRateLimiter({ capacity: 3, windowMs: 10, clock: () => now });
  limiter.check("__proto__");
  limiter.check("idle");
  now = 6;
  limiter.check("__proto__");
  now = 10;
  expect(limiter.cleanup()).toBe(1);
  expect(limiter.check("__proto__")).toEqual({ allowed: true, remaining: 1 });
  now = 20;
  expect(limiter.cleanup()).toBe(1);
  expect(limiter.cleanup()).toBe(0);
  expect(limiter.check("__proto__")).toEqual({ allowed: true, remaining: 2 });
});

test("separate limiter instances do not share quota histories", () => {
  const options = { capacity: 1, windowMs: 50, clock: () => 0 };
  const first = new SlidingWindowRateLimiter(options);
  const second = new SlidingWindowRateLimiter(options);
  first.check("tenant");
  expect(first.check("tenant").allowed).toBe(false);
  expect(second.check("tenant").allowed).toBe(true);
});

test("cleanup and check each observe the injected clock once", () => {
  let reads = 0;
  const limiter = new SlidingWindowRateLimiter({ capacity: 2, windowMs: 7, clock: () => { reads += 1; return 10; } });
  limiter.check("x");
  expect(reads).toBe(1);
  limiter.cleanup();
  expect(reads).toBe(2);
});

test("negative monotonic times and a large jump preserve boundary behavior", () => {
  let now = -100;
  const limiter = new SlidingWindowRateLimiter({ capacity: 1, windowMs: 10, clock: () => now });
  expect(limiter.check("a").allowed).toBe(true);
  now = -90;
  expect(limiter.check("a").allowed).toBe(true);
  now = 1000000;
  expect(limiter.cleanup()).toBe(1);
  expect(limiter.check("a").remaining).toBe(0);
});
