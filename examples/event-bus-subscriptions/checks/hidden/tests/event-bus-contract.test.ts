import { test, expect } from "vitest";
import { EventBus } from "../src/bus";

// Each test names the TICKET clause it covers (C1 to C8).

const NO_THROW = Symbol("emit did not throw");

function thrownBy(action: () => unknown): unknown {
  try {
    action();
  } catch (error) {
    return error;
  }
  return NO_THROW;
}

function errorsOf(thrown: unknown): unknown[] {
  return (thrown as AggregateError).errors;
}

// ---- C1 topics ----

test("C1 topics match by exact string, including case and the empty string", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("User.Created", () => log.push("upper"));
  bus.on("user.created", () => log.push("lower"));
  bus.on("", () => log.push("empty"));
  expect(bus.emit("user.created")).toBe(1);
  expect(bus.emit("")).toBe(1);
  expect(bus.emit("User.Created")).toBe(1);
  expect(bus.emit("user")).toBe(0);
  expect(log).toEqual(["lower", "empty", "upper"]);
});

test("C1 dotted and starred topics are plain strings", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("user.*", () => log.push("user.*"));
  bus.on("*", () => log.push("*"));
  expect(bus.emit("user.created")).toBe(0);
  expect(bus.emit("anything")).toBe(0);
  expect(log).toEqual([]);
  expect(bus.emit("user.*")).toBe(1);
  expect(bus.emit("*")).toBe(1);
  expect(log).toEqual(["user.*", "*"]);
});

test("C1 separate bus instances share no subscriptions", () => {
  const first = new EventBus();
  const second = new EventBus();
  let calls = 0;
  first.on("tick", () => {
    calls += 1;
  });
  expect(second.emit("tick")).toBe(0);
  expect(calls).toBe(0);
  expect(first.emit("tick")).toBe(1);
});

// ---- C2 order and duplicates ----

test("C2 on and once handlers run in registration order", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("t", () => log.push("a"));
  bus.once("t", () => log.push("b"));
  bus.on("t", () => log.push("c"));
  bus.once("t", () => log.push("d"));
  bus.emit("t");
  expect(log).toEqual(["a", "b", "c", "d"]);
  bus.emit("t");
  expect(log).toEqual(["a", "b", "c", "d", "a", "c"]);
});

test("C2 the same function registered twice runs twice per emit", () => {
  const bus = new EventBus();
  let calls = 0;
  const handler = () => {
    calls += 1;
  };
  bus.on("t", handler);
  bus.on("t", handler);
  expect(bus.emit("t")).toBe(2);
  expect(calls).toBe(2);
});

test("C2 on and once of the same function are separate subscriptions", () => {
  const bus = new EventBus();
  let calls = 0;
  const handler = () => {
    calls += 1;
  };
  bus.on("t", handler);
  bus.once("t", handler);
  expect(bus.emit("t")).toBe(2);
  expect(bus.emit("t")).toBe(1);
  expect(calls).toBe(3);
});

// ---- C3 payload ----

test("C3 handlers get exactly one argument which is the same reference", () => {
  const bus = new EventBus();
  const calls: unknown[][] = [];
  const payload = { id: 1, tags: ["a"] };
  bus.on("t", (...args: unknown[]) => calls.push(args));
  bus.once("t", (...args: unknown[]) => calls.push(args));
  bus.emit("t", payload);
  expect(calls).toHaveLength(2);
  for (const args of calls) {
    expect(args).toHaveLength(1);
    expect(args[0]).toBe(payload);
  }
});

test("C3 an omitted payload is delivered as undefined", () => {
  const bus = new EventBus();
  const calls: unknown[][] = [];
  bus.on("t", (...args: unknown[]) => calls.push(args));
  bus.emit("t");
  expect(calls).toEqual([[undefined]]);
  expect(calls[0]).toHaveLength(1);
});

test("C3 falsy payloads are delivered unchanged", () => {
  const bus = new EventBus();
  const seen: unknown[] = [];
  bus.on("t", (value) => seen.push(value));
  for (const value of [0, "", false, null]) {
    bus.emit("t", value);
  }
  expect(seen).toStrictEqual([0, "", false, null]);
});

// ---- C4 return value ----

test("C4 emit returns zero for a topic without subscribers and after all are removed", () => {
  const bus = new EventBus();
  expect(bus.emit("t")).toBe(0);
  const off = bus.on("t", () => {});
  const offOnce = bus.once("t", () => {});
  off();
  offOnce();
  expect(bus.emit("t")).toBe(0);
});

test("C4 emit counts the invocations it made, once handlers included", () => {
  const bus = new EventBus();
  bus.on("t", () => {});
  bus.once("t", () => {});
  bus.on("t", () => {});
  expect(bus.emit("t")).toBe(3);
  expect(bus.emit("t")).toBe(2);
});

test("C4 handlers that return promises are not awaited and emit returns a number", () => {
  const bus = new EventBus();
  bus.on("t", () => Promise.resolve("ignored"));
  bus.once("t", () => Promise.resolve("ignored"));
  const result = bus.emit("t");
  expect(result).toBe(2);
  expect(typeof result).toBe("number");
});

// ---- C5 unsubscribe ----

test("C5 unsubscribe removes only its own subscription from later emits", () => {
  const bus = new EventBus();
  const log: string[] = [];
  const offA = bus.on("t", () => log.push("a"));
  bus.on("t", () => log.push("b"));
  bus.emit("t");
  offA();
  bus.emit("t");
  expect(log).toEqual(["a", "b", "b"]);
});

test("C5 unsubscribe is idempotent and never removes a duplicate registration", () => {
  const bus = new EventBus();
  let calls = 0;
  const handler = () => {
    calls += 1;
  };
  const first = bus.on("t", handler);
  bus.on("t", handler);
  first();
  first();
  first();
  expect(bus.emit("t")).toBe(1);
  expect(calls).toBe(1);
});

test("C5 unsubscribing a once handler before it runs prevents it from ever running", () => {
  const bus = new EventBus();
  let calls = 0;
  const off = bus.once("t", () => {
    calls += 1;
  });
  off();
  expect(bus.emit("t")).toBe(0);
  expect(calls).toBe(0);
});

test("C5 unsubscribing a once handler after it ran does nothing", () => {
  const bus = new EventBus();
  const log: string[] = [];
  const off = bus.once("t", () => log.push("once"));
  bus.on("t", () => log.push("on"));
  bus.emit("t");
  off();
  off();
  bus.emit("t");
  expect(log).toEqual(["once", "on", "on"]);
});

test("C5 remaining subscriptions keep their order after removals and additions", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("t", () => log.push("a"));
  const offB = bus.on("t", () => log.push("b"));
  bus.on("t", () => log.push("c"));
  offB();
  bus.on("t", () => log.push("d"));
  bus.emit("t");
  expect(log).toEqual(["a", "c", "d"]);
});

test("C5 a handler can unsubscribe itself", () => {
  const bus = new EventBus();
  const log: string[] = [];
  const off = bus.on("t", () => {
    log.push("self");
    off();
  });
  bus.on("t", () => log.push("next"));
  expect(bus.emit("t")).toBe(2);
  expect(bus.emit("t")).toBe(1);
  expect(log).toEqual(["self", "next", "next"]);
});

// ---- C6 snapshot ----

test("C6 a handler added during emit runs from the next emit", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let added = false;
  bus.on("t", () => {
    log.push("first");
    if (!added) {
      added = true;
      bus.on("t", () => log.push("added"));
    }
  });
  expect(bus.emit("t")).toBe(1);
  expect(log).toEqual(["first"]);
  expect(bus.emit("t")).toBe(2);
  expect(log).toEqual(["first", "first", "added"]);
});

test("C6 a once handler added during emit runs once from the next emit", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let added = false;
  bus.on("t", () => {
    log.push("first");
    if (!added) {
      added = true;
      bus.once("t", () => log.push("added once"));
    }
  });
  expect(bus.emit("t")).toBe(1);
  expect(bus.emit("t")).toBe(2);
  expect(bus.emit("t")).toBe(1);
  expect(log).toEqual(["first", "first", "added once", "first"]);
});

test("C6 a handler removed by an earlier handler still runs in the current emit only", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let offSecond: () => void = () => {};
  bus.on("t", () => {
    log.push("first");
    offSecond();
  });
  offSecond = bus.on("t", () => log.push("second"));
  expect(bus.emit("t")).toBe(2);
  expect(log).toEqual(["first", "second"]);
  expect(bus.emit("t")).toBe(1);
  expect(log).toEqual(["first", "second", "first"]);
});

test("C6 re-adding a function during emit does not run it again in that emit", () => {
  const bus = new EventBus();
  let calls = 0;
  const handler = () => {
    calls += 1;
  };
  let again = true;
  bus.on("t", () => {
    if (again) {
      again = false;
      bus.on("t", handler);
    }
  });
  bus.on("t", handler);
  bus.emit("t");
  expect(calls).toBe(1);
  bus.emit("t");
  expect(calls).toBe(3);
});

test("C6 a nested emit captures its own snapshot after an unsubscribe", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let nested = false;
  let offSecond: () => void = () => {};
  bus.on("t", () => {
    log.push("first");
    if (!nested) {
      nested = true;
      offSecond();
      log.push("nested count " + bus.emit("t"));
    }
  });
  offSecond = bus.on("t", () => log.push("second"));
  expect(bus.emit("t")).toBe(2);
  expect(log).toEqual(["first", "first", "nested count 1", "second"]);
});

test("C6 a nested emit on another topic uses that topic's subscriptions", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("outer", () => {
    log.push("outer 1");
    log.push("inner count " + bus.emit("inner"));
  });
  bus.on("inner", () => log.push("inner"));
  bus.on("outer", () => log.push("outer 2"));
  expect(bus.emit("outer")).toBe(2);
  expect(log).toEqual(["outer 1", "inner", "inner count 1", "outer 2"]);
});

// ---- C7 once ----

test("C7 a once handler runs for the first emit only", () => {
  const bus = new EventBus();
  let calls = 0;
  bus.once("t", () => {
    calls += 1;
  });
  bus.emit("t");
  bus.emit("t");
  bus.emit("t");
  expect(calls).toBe(1);
});

test("C7 several once handlers each run once in registration order", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.once("t", () => log.push("a"));
  bus.once("t", () => log.push("b"));
  expect(bus.emit("t")).toBe(2);
  expect(bus.emit("t")).toBe(0);
  expect(log).toEqual(["a", "b"]);
});

test("C7 a throwing once handler stays consumed", () => {
  const bus = new EventBus();
  const failure = new Error("once failed");
  let calls = 0;
  bus.once("t", () => {
    calls += 1;
    throw failure;
  });
  const thrown = thrownBy(() => bus.emit("t"));
  expect(thrown).toBeInstanceOf(AggregateError);
  expect(errorsOf(thrown)).toEqual([failure]);
  expect(bus.emit("t")).toBe(0);
  expect(calls).toBe(1);
});

test("C7 a once handler that emits its own topic is not called again", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.once("t", () => {
    log.push("once start");
    log.push("nested count " + bus.emit("t"));
    log.push("once end");
  });
  bus.on("t", () => log.push("on"));
  expect(bus.emit("t")).toBe(2);
  expect(log).toEqual(["once start", "on", "nested count 1", "once end", "on"]);
});

test("C7 a nested emit consumes a once handler before the outer emit reaches it", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let nested = false;
  let nestedCount = -1;
  bus.on("tick", () => {
    log.push("first");
    if (!nested) {
      nested = true;
      nestedCount = bus.emit("tick");
    }
  });
  bus.once("tick", () => log.push("once"));
  bus.on("tick", () => log.push("last"));
  expect(bus.emit("tick")).toBe(2);
  expect(nestedCount).toBe(3);
  expect(log).toEqual(["first", "first", "once", "last", "last"]);
});

test("C7 unsubscribing a captured once handler does not cancel its turn in the current emit", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let offOnce: () => void = () => {};
  bus.on("t", () => {
    log.push("first");
    offOnce();
  });
  offOnce = bus.once("t", () => log.push("once"));
  expect(bus.emit("t")).toBe(2);
  expect(log).toEqual(["first", "once"]);
  expect(bus.emit("t")).toBe(1);
  expect(log).toEqual(["first", "once", "first"]);
});

// ---- C8 errors ----

test("C8 a throwing handler does not stop later handlers of the snapshot", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("t", () => log.push("a"));
  bus.on("t", () => {
    throw new Error("b failed");
  });
  bus.on("t", () => log.push("c"));
  const thrown = thrownBy(() => bus.emit("t"));
  expect(thrown).toBeInstanceOf(AggregateError);
  expect(log).toEqual(["a", "c"]);
});

test("C8 the AggregateError lists thrown values in invocation order", () => {
  const bus = new EventBus();
  const e1 = new Error("one");
  const e2 = new RangeError("two");
  const e3 = new TypeError("three");
  bus.on("t", () => {
    throw e1;
  });
  bus.on("t", () => {});
  bus.once("t", () => {
    throw e2;
  });
  bus.on("t", () => {
    throw e3;
  });
  const errors = errorsOf(thrownBy(() => bus.emit("t")));
  expect(errors).toHaveLength(3);
  expect(errors[0]).toBe(e1);
  expect(errors[1]).toBe(e2);
  expect(errors[2]).toBe(e3);
});

test("C8 one failure still produces an AggregateError with one entry", () => {
  const bus = new EventBus();
  const failure = new Error("only");
  bus.on("t", () => {
    throw failure;
  });
  const thrown = thrownBy(() => bus.emit("t"));
  expect(thrown).toBeInstanceOf(AggregateError);
  expect(thrown).not.toBe(failure);
  expect(errorsOf(thrown)).toHaveLength(1);
  expect(errorsOf(thrown)[0]).toBe(failure);
});

test("C8 thrown values that are not errors are collected unchanged", () => {
  const bus = new EventBus();
  const marker = { reason: "object" };
  bus.on("t", () => {
    throw "text";
  });
  bus.on("t", () => {
    throw undefined;
  });
  bus.on("t", () => {
    throw 42;
  });
  bus.on("t", () => {
    throw marker;
  });
  const errors = errorsOf(thrownBy(() => bus.emit("t")));
  expect(errors).toHaveLength(4);
  expect(errors[0]).toBe("text");
  expect(errors[1]).toBe(undefined);
  expect(errors[2]).toBe(42);
  expect(errors[3]).toBe(marker);
});

test("C8 a nested emit that fails is collected as one entry", () => {
  const bus = new EventBus();
  const inner = new Error("inner failed");
  bus.on("inner", () => {
    throw inner;
  });
  bus.on("outer", () => {
    bus.emit("inner");
  });
  bus.on("outer", () => {});
  const outerErrors = errorsOf(thrownBy(() => bus.emit("outer")));
  expect(outerErrors).toHaveLength(1);
  expect(outerErrors[0]).toBeInstanceOf(AggregateError);
  expect(errorsOf(outerErrors[0])).toHaveLength(1);
  expect(errorsOf(outerErrors[0])[0]).toBe(inner);
});

test("C8 emit does not throw when no handler throws", () => {
  const bus = new EventBus();
  bus.on("t", () => {});
  bus.once("t", () => {});
  expect(thrownBy(() => bus.emit("t"))).toBe(NO_THROW);
});

test("C8 the bus stays usable after a failed emit", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.once("t", () => {
    log.push("once");
    throw new Error("once failed");
  });
  bus.on("t", () => log.push("kept"));
  expect(thrownBy(() => bus.emit("t"))).toBeInstanceOf(AggregateError);
  expect(bus.emit("t")).toBe(1);
  expect(log).toEqual(["once", "kept", "kept"]);
});

test("C8 a handler that throws on every emit stays subscribed", () => {
  const bus = new EventBus();
  let calls = 0;
  bus.on("t", () => {
    calls += 1;
    throw new Error("always");
  });
  expect(thrownBy(() => bus.emit("t"))).toBeInstanceOf(AggregateError);
  expect(thrownBy(() => bus.emit("t"))).toBeInstanceOf(AggregateError);
  expect(calls).toBe(2);
});

test("C8 changes made by a handler before it throws still apply", () => {
  const bus = new EventBus();
  const log: string[] = [];
  let offLater: () => void = () => {};
  bus.on("t", () => {
    bus.on("t", () => log.push("added"));
    offLater();
    throw new Error("after changes");
  });
  offLater = bus.on("t", () => log.push("later"));
  expect(thrownBy(() => bus.emit("t"))).toBeInstanceOf(AggregateError);
  expect(log).toEqual(["later"]);
  expect(thrownBy(() => bus.emit("t"))).toBeInstanceOf(AggregateError);
  expect(log).toEqual(["later", "added"]);
});
