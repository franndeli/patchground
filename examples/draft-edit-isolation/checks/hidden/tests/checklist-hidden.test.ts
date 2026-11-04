import { expect, test } from "vitest";
import { begin_edit, cancel_edit, save_edit } from "../src/checklist";
import type { Checklist } from "../src/checklist";

function record(): Checklist {
  return {
    name: "Cargo",
    items: [
      { id: "__proto__", label: "Latch", completed: false },
      { id: "B", label: "Ramp", completed: true },
      { id: "b", label: "Lights", completed: false },
    ],
  };
}

test("hidden draft nested changes cannot reach saved items", () => {
  const saved = record();
  const draft = begin_edit(saved);
  for (const item of draft.items) {
    item.label += " changed";
    item.completed = !item.completed;
    item.id += "-draft";
  }
  expect(saved).toEqual(record());
});

test("hidden saved mutations cannot reach existing drafts", () => {
  const saved = record();
  const draft = begin_edit(saved);
  for (const item of saved.items) item.completed = true;
  saved.items.pop();
  saved.name = "Replaced";
  expect(draft).toEqual(record());
});

test("hidden two simultaneous drafts own separate arrays and child objects", () => {
  const saved = record();
  const first = begin_edit(saved);
  const second = begin_edit(saved);
  for (const item of first.items) item.label = "Edited";
  first.items.reverse();
  first.items.push({ id: "extra", label: "Extra", completed: false });
  expect(second).toEqual(record());
  expect(saved).toEqual(record());
});

test("hidden cancellation leaves draft contents alone and saved contents intact", () => {
  const saved = record();
  const draft = begin_edit(saved);
  draft.items.splice(1, 1);
  for (const item of draft.items) item.completed = true;
  const beforeCancel = JSON.stringify(draft);
  expect(cancel_edit(draft)).toBeNull();
  expect(JSON.stringify(draft)).toBe(beforeCancel);
  expect(saved).toEqual(record());
});

test("hidden saving independent inputs leaves them untouched and isolates the output", () => {
  const saved = record();
  const draft = record();
  draft.items.reverse();
  draft.name = " Cargo revised ";
  const expected = JSON.stringify(draft);
  const result = save_edit(saved, draft);
  if (!result.ok) throw new Error("Expected valid draft");
  expect(JSON.stringify(result.saved)).toBe(expected);
  expect(JSON.stringify(draft)).toBe(expected);
  expect(saved).toEqual(record());
  for (const item of result.saved.items) item.label = "Output edit";
  result.saved.items.pop();
  expect(JSON.stringify(draft)).toBe(expected);
  expect(saved).toEqual(record());
});

test("hidden save protects its result from later edits to either original argument", () => {
  const saved = record();
  const draft = begin_edit(saved);
  const result = save_edit(saved, draft);
  if (!result.ok) throw new Error("Expected valid draft");
  for (const item of saved.items) item.label = "Source edit";
  for (const item of draft.items) item.completed = true;
  draft.items.length = 0;
  expect(result.saved).toEqual(record());
});

test("hidden validation follows documented first-error order", () => {
  const saved = record();
  expect(save_edit(saved, { name: "\t", items: [] })).toEqual({
    ok: false, error: { code: "blank_name", path: "name" },
  });
  expect(save_edit(saved, {
    name: "Ready",
    items: [
      { id: "same", label: "Good", completed: false },
      { id: "same", label: "\t\n", completed: false },
    ],
  })).toEqual({
    ok: false, error: { code: "blank_label", path: "items[1].label" },
  });
  expect(save_edit(saved, {
    name: "Ready",
    items: [
      { id: "same", label: "Good", completed: false },
      { id: "same", label: "Also good", completed: false },
      { id: "later", label: "", completed: false },
    ],
  })).toEqual({
    ok: false, error: { code: "duplicate_id", path: "items[1].id" },
  });
});

test("hidden failed validation can be corrected without corrupting saved state", () => {
  const saved = record();
  const draft = begin_edit(saved);
  for (const item of draft.items) item.label = " ";
  const before = JSON.stringify(draft);
  expect(save_edit(saved, draft)).toEqual({
    ok: false, error: { code: "blank_label", path: "items[0].label" },
  });
  expect(JSON.stringify(draft)).toBe(before);
  expect(saved).toEqual(record());
  for (const item of draft.items) item.label = "Verified";
  const result = save_edit(saved, draft);
  expect(result.ok).toBe(true);
  expect(saved).toEqual(record());
});

test("hidden repeated editing sessions preserve earlier saved values", () => {
  const original = record();
  const first = begin_edit(original);
  first.name = "Second revision";
  const result = save_edit(original, first);
  if (!result.ok) throw new Error("Expected first save");
  const expected = JSON.stringify(result.saved);
  const next = begin_edit(result.saved);
  for (const item of next.items) item.completed = !item.completed;
  next.items.shift();
  expect(cancel_edit(next)).toBeNull();
  expect(JSON.stringify(result.saved)).toBe(expected);
  expect(original).toEqual(record());
});

test("hidden exact ID equality permits distinct casing and detects nonadjacent duplicates", () => {
  const draft = record();
  expect(save_edit(record(), draft)).toEqual({ ok: true, saved: draft });
  draft.items.push({ id: "__proto__", label: "Duplicate latch", completed: false });
  expect(save_edit(record(), draft)).toEqual({
    ok: false, error: { code: "duplicate_id", path: "items[3].id" },
  });
});
