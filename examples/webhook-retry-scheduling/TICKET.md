# Keep webhook failures from blocking other deliveries

A notification worker holds deliveries in an in-memory queue. It can already send
due items and retire successes and permanent rejections, but temporary failures
are currently lost. Add bounded retry scheduling without sleeping or repeatedly
attempting the same item inside a drain.

## Public interface and state

Work in `workspace/src/webhook_queue.py`. Keep these supplied interfaces:

- `DeliveryQueue(sender)` takes a callable `sender(Delivery) -> Response`.
- `enqueue(delivery_id: str, payload: str, due_at: int) -> None` adds a delivery.
  New IDs start `pending` with zero attempts and the supplied due time.
  Repeating an ID is a no-op regardless of its state: retain its original payload,
  attempts, due time and status.
- `drain(now: int) -> tuple[str, ...]` attempts due deliveries and returns their
  IDs in attempt order.
- `get(delivery_id: str) -> Delivery` exposes an immutable state snapshot. Retained
  snapshots must not change as later drains update the queue.
- A `Delivery` has `delivery_id`, `payload`, `status`, `attempts`, and
  `due_at`. Status is `pending`, `complete`, `failed` (permanent), or
  `exhausted`. Terminal states have `due_at=None`.
- `Response(status_code: int, retry_after_ms: object = None)` describes a sender
  response. The sender may instead raise Python's built-in `TimeoutError`.
  All other sender exception types are outside this task.

IDs and payloads are prevalidated strings; due times and injected `now` are
integer milliseconds on the same monotonic clock. The clock is supplied by callers,
not read from the operating system. There is no remote sender: the supplied
`ScriptedSender` in `scripted_sender.py` accepts per-ID response/timeout
sequences and records immutable delivery snapshots in `calls`.

## Drain and retry rules

1. On each drain, select all pending items with `due_at <= now`. Attempt each
   selected item at most once in ascending `(due_at, delivery_id)` order, including
   ties resolved by ordinary case-sensitive Python string ordering.
   Future items remain completely unchanged. Continue to unrelated due items after
   a timeout, rate limit, server error or permanent rejection.
2. Increment attempts for every send, including timeouts. The sender sees the
   incremented attempt count, original due time, and pending status.
3. Any 2xx response marks `complete`. A timeout, 429 or any 5xx is retryable.
   Every other integer status marks `failed`, including 3xx and other 4xx.
4. Allow **three total attempts**, including the initial send. After retryable
   failure on attempt 1, schedule `now + 1000`; after attempt 2,
   schedule `now + 2000`. Keep status `pending` while waiting.
   Compute from this drain's `now`, not from the original due time.
5. Only on 429, use the larger of the normal delay and `retry_after_ms`, if it
   is a nonnegative integer duration. Zero is valid. Missing, negative,
   boolean, float, string or other invalid values fall back to the normal delay.
   Ignore retry-after on every other status.
6. A third retryable failure marks `exhausted` with `due_at=None`, regardless
   of retry-after. Success on attempt 3 still completes; a permanent rejection on
   any attempt still fails permanently.
7. Completed, failed and exhausted items must never be sent again, even after
   duplicate enqueue or arbitrarily late drains. An empty/no-due drain returns `()`.

## Scope and verification

This is a single-worker deterministic queue, not a service. Use the standard library;
no sleeps, threads, network, external queues, persistence, restart recovery, concurrent
workers or exactly-once guarantees. Duplicate-ID handling is queue identity only.
Sender reentrancy and arbitrary infrastructure failures are outside scope.

Visible tests are in `checks/visible/tests/` and arrive as `tests/` in a session.
Add conventional tests where useful without changing the supplied interfaces or
runner configuration. Use Patchground's Docker commands for checks, never host pytest.

The advanced 75-minute estimate is provisional, not human-calibrated. This is
an original model-generated Patchground exercise, not an employer's interview.
