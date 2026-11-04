import { expect, test } from "vitest";
import { SearchModel } from "../src/search-model";

function deferred() {
  let resolve = (_value: string[]): void => {};
  let reject = (_reason: unknown): void => {};
  const promise = new Promise<string[]>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test("hidden old success cannot end a newer loading state", async () => {
  const one = deferred();
  const two = deferred();
  const model = new SearchModel((q) => q === "one" ? one.promise : two.promise);
  const first = model.search("one");
  const second = model.search("two");
  one.resolve(["Obsolete"]);
  await first;
  expect(model.get_state()).toEqual({
    kind: "loading", query: "two", results: [], error: null,
  });
  two.resolve(["Two", "One"]);
  await second;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "two", results: ["Two", "One"], error: null,
  });
});

test("hidden old failure cannot end newer loading", async () => {
  const one = deferred();
  const two = deferred();
  const model = new SearchModel((q) => q === "one" ? one.promise : two.promise);
  const first = model.search("one");
  const second = model.search("two");
  one.reject(new Error("Obsolete error"));
  await expect(first).resolves.toBeUndefined();
  expect(model.get_state()).toEqual({
    kind: "loading", query: "two", results: [], error: null,
  });
  two.reject(new Error("Current error"));
  await second;
  expect(model.get_state()).toEqual({
    kind: "error", query: "two", results: [], error: "Current error",
  });
});

test("hidden an earlier success cannot erase the latest failure", async () => {
  const first = deferred();
  const last = deferred();
  const model = new SearchModel((q) => q === "first" ? first.promise : last.promise);
  const a = model.search("first");
  const b = model.search("last");
  last.reject(new Error("Newest failed"));
  await b;
  first.resolve(["No longer relevant"]);
  await a;
  expect(model.get_state()).toEqual({
    kind: "error", query: "last", results: [], error: "Newest failed",
  });
});

test("hidden an earlier failure cannot erase the latest failure", async () => {
  const first = deferred();
  const last = deferred();
  const model = new SearchModel((q) => q === "first" ? first.promise : last.promise);
  const a = model.search("first");
  const b = model.search("last");
  last.reject(new Error("Newest failed"));
  await b;
  first.reject(new Error("Old failed"));
  await a;
  expect(model.get_state()).toEqual({
    kind: "error", query: "last", results: [], error: "Newest failed",
  });
});

test("hidden repeated text starts distinct requests and rejects stale failure", async () => {
  const first = deferred();
  const second = deferred();
  let count = 0;
  const calls: string[] = [];
  const model = new SearchModel((q) => {
    calls.push(q);
    count += 1;
    return count === 1 ? first.promise : second.promise;
  });
  const a = model.search("\n rack ");
  const b = model.search("rack");
  second.resolve(["Latest rack"]);
  await b;
  first.reject(null);
  await expect(a).resolves.toBeUndefined();
  expect(calls).toEqual(["rack", "rack"]);
  expect(model.get_state()).toEqual({
    kind: "ready", query: "rack", results: ["Latest rack"], error: null,
  });
});

test("hidden clear invalidates multiple successes and failures", async () => {
  const one = deferred();
  const two = deferred();
  let count = 0;
  const model = new SearchModel(() => ++count === 1 ? one.promise : two.promise);
  const a = model.search("a");
  const b = model.search("b");
  const clearing = model.search("\n\t");
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
  await clearing;
  two.reject(new Error("Cleared"));
  one.resolve(["Cleared"]);
  await Promise.all([a, b]);
  expect(count).toBe(2);
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
});

test("hidden clear and requery do not revive an older identical query", async () => {
  const old = deferred();
  const fresh = deferred();
  let count = 0;
  const model = new SearchModel(() => ++count === 1 ? old.promise : fresh.promise);
  const a = model.search("same");
  await model.search("");
  const b = model.search("same");
  fresh.resolve(["Fresh"]);
  await b;
  old.resolve(["Stale"]);
  await a;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "same", results: ["Fresh"], error: null,
  });
});

test("hidden disposal suppresses rejection and does not reset loading state", async () => {
  const pending = deferred();
  const model = new SearchModel(() => pending.promise);
  const task = model.search("pending");
  model.dispose();
  pending.reject(new Error("After disposal"));
  await expect(task).resolves.toBeUndefined();
  expect(model.get_state()).toEqual({
    kind: "loading", query: "pending", results: [], error: null,
  });
});

test("hidden disposal before first search makes every later search a no-op", async () => {
  let count = 0;
  const model = new SearchModel(() => {
    count += 1;
    return Promise.resolve(["Unexpected"]);
  });
  model.dispose();
  await model.search("first");
  await model.search(" ");
  model.dispose();
  expect(count).toBe(0);
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
});

test("hidden current failures clear previous results and fallback for non-Errors", async () => {
  const pending = deferred();
  const calls: string[] = [];
  const model = new SearchModel((q) => {
    calls.push(q);
    return calls.length === 1 ? Promise.resolve(["Prior"]) : pending.promise;
  });
  await model.search("good");
  const task = model.search(" bad ");
  expect(model.get_state()).toEqual({
    kind: "loading", query: "bad", results: [], error: null,
  });
  pending.reject({ message: "Not an Error instance" });
  await task;
  expect(model.get_state()).toEqual({
    kind: "error", query: "bad", results: [], error: "Search failed",
  });
  expect(calls).toEqual(["good", "bad"]);
});

test("hidden an empty success stays ready and a clear removes a settled error", async () => {
  let count = 0;
  const model = new SearchModel(() => {
    count += 1;
    return count === 1 ? Promise.resolve([]) : Promise.reject(new Error(""));
  });
  await model.search("none");
  expect(model.get_state()).toEqual({
    kind: "ready", query: "none", results: [], error: null,
  });
  await model.search("failure");
  expect(model.get_state()).toEqual({
    kind: "error", query: "failure", results: [], error: "",
  });
  await model.search("  ");
  expect(count).toBe(2);
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
});

test("hidden three requests retain the latest across two reverse stale completions", async () => {
  const one = deferred();
  const two = deferred();
  const three = deferred();
  const model = new SearchModel((q) => q === "1" ? one.promise : q === "2" ? two.promise : three.promise);
  const a = model.search("1");
  const b = model.search("2");
  const c = model.search("3");
  three.resolve(["Z", "A", "Z"]);
  await c;
  two.reject(new Error("Second stale"));
  await b;
  one.resolve(["First stale"]);
  await a;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "3", results: ["Z", "A", "Z"], error: null,
  });
});

test("hidden separate model instances do not invalidate each other's searches", async () => {
  const first = deferred();
  const second = deferred();
  const a = new SearchModel(() => first.promise);
  const b = new SearchModel(() => second.promise);
  const taskA = a.search("alpha");
  const taskB = b.search("beta");
  a.dispose();
  second.resolve(["Beta"]);
  first.resolve(["Alpha"]);
  await Promise.all([taskA, taskB]);
  expect(b.get_state()).toEqual({
    kind: "ready", query: "beta", results: ["Beta"], error: null,
  });
  expect(a.get_state()).toEqual({
    kind: "loading", query: "alpha", results: [], error: null,
  });
});
