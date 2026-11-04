import { expect, test } from "vitest";
import { SearchModel } from "../src/search-model";

function controlled() {
  let resolve = (_value: string[]): void => {};
  let reject = (_reason: unknown): void => {};
  const promise = new Promise<string[]>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test("search trims its query and immediately clears previous results", async () => {
  const pending = controlled();
  const calls: string[] = [];
  const model = new SearchModel((query) => {
    calls.push(query);
    return pending.promise;
  });
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
  const task = model.search("  bolts \t");
  expect(calls).toEqual(["bolts"]);
  expect(model.get_state()).toEqual({
    kind: "loading", query: "bolts", results: [], error: null,
  });
  pending.resolve(["B-9", "B-2"]);
  await task;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "bolts", results: ["B-9", "B-2"], error: null,
  });
  const next = model.search("nuts");
  expect(model.get_state()).toEqual({
    kind: "loading", query: "nuts", results: [], error: null,
  });
  await next;
});

test("an older success cannot overwrite a newer success", async () => {
  const old = controlled();
  const latest = controlled();
  const model = new SearchModel((query) => query === "old" ? old.promise : latest.promise);
  const first = model.search("old");
  const second = model.search("new");
  latest.resolve(["New part"]);
  await second;
  old.resolve(["Old part"]);
  await first;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "new", results: ["New part"], error: null,
  });
});

test("a current failure is handled and a new request clears its error", async () => {
  const failed = controlled();
  const recovery = controlled();
  const model = new SearchModel((query) => query === "failed" ? failed.promise : recovery.promise);
  const first = model.search("failed");
  failed.reject(new Error("Catalog unavailable"));
  await expect(first).resolves.toBeUndefined();
  expect(model.get_state()).toEqual({
    kind: "error", query: "failed", results: [], error: "Catalog unavailable",
  });
  const second = model.search("retry");
  expect(model.get_state()).toEqual({
    kind: "loading", query: "retry", results: [], error: null,
  });
  recovery.resolve([]);
  await second;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "retry", results: [], error: null,
  });
});

test("a stale failure cannot replace later successful results", async () => {
  const old = controlled();
  const latest = controlled();
  const model = new SearchModel((query) => query === "old" ? old.promise : latest.promise);
  const first = model.search("old");
  const second = model.search("latest");
  latest.resolve(["Current"]);
  await second;
  old.reject(new Error("Old failure"));
  await expect(first).resolves.toBeUndefined();
  expect(model.get_state()).toEqual({
    kind: "ready", query: "latest", results: ["Current"], error: null,
  });
});

test("clearing invalidates pending work without calling the transport", async () => {
  const pending = controlled();
  const calls: string[] = [];
  const model = new SearchModel((query) => {
    calls.push(query);
    return pending.promise;
  });
  const task = model.search("washer");
  await model.search(" \t\n ");
  expect(calls).toEqual(["washer"]);
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
  pending.resolve(["Must stay hidden"]);
  await task;
  expect(model.get_state()).toEqual({
    kind: "idle", query: "", results: [], error: null,
  });
});

test("repeating a query still gives the newer request ownership", async () => {
  const old = controlled();
  const latest = controlled();
  let calls = 0;
  const model = new SearchModel(() => ++calls === 1 ? old.promise : latest.promise);
  const first = model.search("bolt");
  const second = model.search(" bolt ");
  expect(calls).toBe(2);
  latest.resolve(["New batch"]);
  await second;
  old.resolve(["Old batch"]);
  await first;
  expect(model.get_state()).toEqual({
    kind: "ready", query: "bolt", results: ["New batch"], error: null,
  });
});

test("disposal preserves state and ignores in-flight completion and later calls", async () => {
  const pending = controlled();
  let calls = 0;
  const model = new SearchModel(() => {
    calls += 1;
    return pending.promise;
  });
  const task = model.search("hinge");
  const before = model.get_state();
  model.dispose();
  model.dispose();
  await model.search("next");
  await model.search("");
  pending.resolve(["Late"]);
  await task;
  expect(calls).toBe(1);
  expect(model.get_state()).toEqual(before);
});

test("a non-Error rejection has the documented fallback message", async () => {
  const model = new SearchModel(() => Promise.reject("offline"));
  await expect(model.search("bracket")).resolves.toBeUndefined();
  expect(model.get_state()).toEqual({
    kind: "error", query: "bracket", results: [], error: "Search failed",
  });
});
