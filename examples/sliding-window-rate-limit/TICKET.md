# Enforce a rolling request quota

The partner-preview API already converts admission decisions into HTTP-shaped
responses in `src/request-gate.ts`. Its new in-memory quota policy is unfinished.
Complete `SlidingWindowRateLimiter` in `src/rate-limiter.ts` without changing
the adapter's response contract.

## Public interface

Construct with `new SlidingWindowRateLimiter({ capacity, windowMs, clock })`.
Both numeric options must be positive integers; otherwise throw `RangeError`.
The injected `clock: () => number` returns a monotonic integer millisecond time.
It may return the same timestamp repeatedly. Each check or cleanup reads it
exactly once so that operation uses a single time snapshot. Clock regression
and invalid clock outputs are outside scope.

- `check(clientId: string): { allowed: boolean; remaining: number }`
  considers only this client's **accepted** timestamps strictly greater than
  `now - windowMs`. Expire older timestamps before deciding. Admit when fewer
  than `capacity` remain, record the accepted request, and report capacity
  remaining **after** this call. Rejection returns false and zero remaining.
- Rejected requests do not consume capacity, extend expiry, or postpone a later
  admission. Calls at the same timestamp are distinct requests.
- All string client IDs are valid, including the empty string, `__proto__`,
  `constructor`, and `toString`. Histories are independent.
- `cleanup(): number` uses the injected time to prune expired accepted
  timestamps for **all** tracked clients, including idle ones. Remove clients
  with no live history and return the number of client histories removed
  (not the number of requests removed). Calling cleanup again without new
  expiration returns zero. Preserve still-live capacity consumption. Cleanup
  on a new limiter returns zero. Admission also expires the requesting client's
  history, so correctness must not depend on a cleanup call.

For capacity 2 and windowMs 100: accepts at 0 and 50 fill the quota; a call at
99 is rejected; a call at 100 expires only timestamp 0 and is accepted with
zero remaining. A rejection at 99 must not change this outcome.

## Working boundaries

Keep the injected clock and public interfaces. Add tests under `tests/`.
Visible checks are supplied there by Patchground; verification adds independent
checks. Run checks through Patchground's Docker environment, not host npm.
Do not add Redis, networking, timers, sleeps, background jobs, or dependencies.
This is a single-process exercise, not a distributed rate limiter.

The implementation and checks are original generated practice material.
The intermediate difficulty and 45-minute timebox are provisional author estimates,
not measured human completion times or claims about an employer interview.
