import { test, expect } from "vitest";
import { SlidingWindowRateLimiter } from "../src/rate-limiter.js";
import { gateRequest } from "../src/request-gate.js";

test("quota reports capacity after each same-time request", () => {
  const limiter = new SlidingWindowRateLimiter({ capacity: 2, windowMs: 100, clock: () => 0 });
  expect(limiter.check("partner")).toEqual({ allowed: true, remaining: 1 });
  expect(limiter.check("partner")).toEqual({ allowed: true, remaining: 0 });
  expect(limiter.check("partner")).toEqual({ allowed: false, remaining: 0 });
});

test("quota expires the exact boundary without extending rejected requests", () => {
  let now = 0;
  const limiter = new SlidingWindowRateLimiter({ capacity: 2, windowMs: 100, clock: () => now });
  limiter.check("partner");
  now = 50;
  limiter.check("partner");
  now = 99;
  expect(limiter.check("partner").allowed).toBe(false);
  now = 100;
  expect(limiter.check("partner")).toEqual({ allowed: true, remaining: 0 });
  now = 150;
  expect(limiter.check("partner")).toEqual({ allowed: true, remaining: 0 });
});

test("quota keeps adversarial client keys independent", () => {
  const limiter = new SlidingWindowRateLimiter({ capacity: 1, windowMs: 25, clock: () => 7 });
  for (const client of ["__proto__", "constructor", "toString", "", "ordinary"]) {
    expect(limiter.check(client)).toEqual({ allowed: true, remaining: 0 });
    expect(limiter.check(client)).toEqual({ allowed: false, remaining: 0 });
  }
});

test("quota cleanup removes idle histories but preserves live limits", () => {
  let now = 0;
  const limiter = new SlidingWindowRateLimiter({ capacity: 1, windowMs: 20, clock: () => now });
  expect(limiter.cleanup()).toBe(0);
  limiter.check("idle");
  now = 5;
  limiter.check("live");
  now = 20;
  expect(limiter.cleanup()).toBe(1);
  expect(limiter.cleanup()).toBe(0);
  expect(limiter.check("live").allowed).toBe(false);
  expect(limiter.check("idle").allowed).toBe(true);
});

test("quota rejects invalid capacity and window options with RangeError", () => {
  for (const invalid of [0, -1, 1.5, NaN, Infinity]) {
    expect(() => new SlidingWindowRateLimiter({ capacity: invalid, windowMs: 10, clock: () => 0 })).toThrow(RangeError);
    expect(() => new SlidingWindowRateLimiter({ capacity: 1, windowMs: invalid, clock: () => 0 })).toThrow(RangeError);
  }
});

test("request gate preserves its HTTP-shaped response contract", () => {
  const limiter = new SlidingWindowRateLimiter({ capacity: 1, windowMs: 10, clock: () => 0 });
  expect(gateRequest(limiter, "preview")).toEqual({ status: 200, headers: { "x-quota-remaining": "0" } });
  expect(gateRequest(limiter, "preview")).toEqual({ status: 429, headers: { "x-quota-remaining": "0" } });
});
