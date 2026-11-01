# Let subscribers unsubscribe and listen once on the event bus

**Reported by:** CLI tooling team
**Component:** `localbus` (`src/bus.ts`)

## Background

`EventBus` is a small synchronous in-process bus. Today `on(topic, handler)` registers a handler and
`emit(topic, payload)` calls the registered handlers in order and returns how many it called. There is
no way to take a subscription back, and no way to listen for a single event. Two stubs exist so callers
can already import the final API: `on` returns an unsubscribe function that does nothing, and `once`
throws "not implemented".

## Request

Make `on` return a working unsubscribe function, implement `once`, and make `emit` safe when handlers
subscribe, unsubscribe, re-enter or throw. All other behavior must stay as it is.

### Public API

```ts
type Handler = (payload: unknown) => void;
type Unsubscribe = () => void;

class EventBus {
  on(topic: string, handler: Handler): Unsubscribe;
  once(topic: string, handler: Handler): Unsubscribe;
  emit(topic: string, payload?: unknown): number;
}
```

The checks run the code at runtime with Vitest. They do not run the TypeScript compiler, so they make
no claim about type correctness.

### Scope

Everything is synchronous. There are no wildcards or patterns, no priorities and no compatibility
with Node's `EventEmitter`. A handler's return value is ignored: if it returns a promise, the bus does
not wait for it and does not look at it.

### Clauses

**C1 Topics.** A topic is any string, compared exactly and case-sensitively; the empty string is a
valid topic. `*`, `.` and similar characters have no special meaning, so `emit("user.created")` never
reaches a handler registered for `"user.*"` or `"*"`. Separate `EventBus` instances share nothing.

**C2 Order and duplicates.** Handlers for a topic run in registration order, whether they were
registered with `on` or `once`. Registering the same function again, with `on` or `once`, creates an
independent subscription; it runs once per subscription per emit and has its own unsubscribe function.

**C3 Payload.** Each handler is called with exactly one argument: the `payload` given to `emit`, the
same value and reference (no copy). If `emit` is called without a payload, handlers receive
`undefined`. Falsy payloads (`0`, `""`, `false`, `null`) are delivered as they are.

**C4 Return value.** `emit` returns the number of handler invocations it made: `0` if the topic has no
subscribers. A `once` subscription that was skipped (C7) is not counted. If any handler throws, `emit`
throws (C8) and returns nothing.

**C5 Unsubscribe.** `on` and `once` return an unsubscribe function for that one subscription. Calling
it removes that subscription from later emits. Calling it again does nothing, and never removes
another subscription, even one that uses the same handler function. Unsubscribing a `once`
subscription that has already run does nothing. Order of the remaining subscriptions is unchanged.

**C6 Snapshot.** When `emit` starts it captures the subscriptions of that topic, in registration
order, and calls exactly those. Subscriptions added during the emit run from the next emit on.
Unsubscribing during the emit takes effect for later emits only: a captured subscription still gets its
turn in the emit that captured it, whether it was registered with `on` or `once`. A nested `emit`
(called from a handler) captures its own snapshot from the subscriptions that exist at that moment.

**C7 Once.** A `once` subscription runs at most once. It is consumed immediately before its handler
is called, so it stays consumed if the handler throws, and a handler that emits its own topic is not
called again. A captured `once` subscription whose turn comes after it was already consumed, for
example by a nested `emit`, is skipped and not counted. Being unsubscribed does not consume it (C6).

Example:

```ts
const bus = new EventBus();
const log: string[] = [];
let nested = false;
bus.on("tick", () => {
  log.push("first");
  if (!nested) {
    nested = true;
    bus.emit("tick"); // returns 3: first, once, last
  }
});
bus.once("tick", () => log.push("once"));
bus.on("tick", () => log.push("last"));
bus.emit("tick"); // returns 2: first, last (the once handler was consumed by the nested emit)
// log: first, first, once, last, last
```

**C8 Errors.** A handler that throws does not stop later handlers of the same snapshot. After the last
captured subscription's turn, if any handler threw, `emit` throws an `AggregateError` whose `errors`
lists the thrown values in invocation order, unchanged (not wrapped, and not only `Error` objects).
One failure still produces an `AggregateError` with one entry. If a handler's own nested `emit` throws
an `AggregateError`, that `AggregateError` is a single entry. The message text is not specified. The
bus stays fully usable: consumed `once` subscriptions stay consumed, other subscriptions stay
registered, and changes made by handlers before or after a failure still apply.

## Notes

- Keep `src/bus.ts` as the module that exports `EventBus`, `Handler` and `Unsubscribe`.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- Add tests for the behavior you implement and keep the existing behavior unchanged.
- You may use your own editor and AI tools. The goal is to build and explain a precise change, not
  only to make the listed cases pass.
