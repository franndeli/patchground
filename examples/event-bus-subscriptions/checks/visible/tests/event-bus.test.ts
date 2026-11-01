import { test, expect } from "vitest";
import { EventBus } from "../src/bus";

test("emit calls the handlers of the exact topic in registration order", () => {
  const bus = new EventBus();
  const log: string[] = [];
  bus.on("user.created", () => log.push("a"));
  bus.on("user.deleted", () => log.push("other topic"));
  bus.on("user.created", () => log.push("b"));
  expect(bus.emit("user.created")).toBe(2);
  expect(log).toEqual(["a", "b"]);
});

test("emit forwards the payload to the handler", () => {
  const bus = new EventBus();
  const seen: unknown[] = [];
  const payload = { id: 7 };
  bus.on("saved", (value) => seen.push(value));
  bus.emit("saved", payload);
  expect(seen[0]).toBe(payload);
});

test("emit returns zero when nothing is subscribed", () => {
  const bus = new EventBus();
  expect(bus.emit("nobody")).toBe(0);
});

test("the function returned by on stops later deliveries", () => {
  const bus = new EventBus();
  let calls = 0;
  const off = bus.on("tick", () => {
    calls += 1;
  });
  bus.emit("tick");
  off();
  bus.emit("tick");
  expect(calls).toBe(1);
});

test("once runs for the first emit only", () => {
  const bus = new EventBus();
  let calls = 0;
  bus.once("tick", () => {
    calls += 1;
  });
  expect(bus.emit("tick")).toBe(1);
  expect(bus.emit("tick")).toBe(0);
  expect(calls).toBe(1);
});

test("a throwing handler does not stop the next one and emit throws an AggregateError", () => {
  const bus = new EventBus();
  const failure = new Error("boom");
  let later = false;
  bus.on("tick", () => {
    throw failure;
  });
  bus.on("tick", () => {
    later = true;
  });
  let caught: unknown;
  try {
    bus.emit("tick");
  } catch (error) {
    caught = error;
  }
  expect(later).toBe(true);
  expect(caught).toBeInstanceOf(AggregateError);
  expect((caught as AggregateError).errors).toEqual([failure]);
});
