import { expect, test } from "vitest";
import { begin_edit, cancel_edit, save_edit } from "../src/checklist";

function shipment() {
  return {
    name: "Outbound van",
    items: [
      { id: "seal", label: "Check seal", completed: false },
      { id: "manifest", label: "Print manifest", completed: true },
    ],
  };
}

test("a draft can change a nested item and cancel without changing saved state", () => {
  const saved = shipment();
  const before = shipment();
  const draft = begin_edit(saved);
  draft.name = "New route";
  for (const item of draft.items) {
    item.label = "Recheck";
    item.completed = !item.completed;
  }
  expect(cancel_edit(draft)).toBeNull();
  expect(saved).toEqual(before);
  expect(draft.name).toBe("New route");
});

test("draft additions and removals stay private", () => {
  const saved = shipment();
  const draft = begin_edit(saved);
  draft.items.splice(0, 1);
  draft.items.push({ id: "photo", label: "Take photo", completed: false });
  expect(saved).toEqual(shipment());
});

test("a valid save preserves values and is isolated from subsequent draft edits", () => {
  const saved = shipment();
  const draft = {
    name: " Night shift ",
    items: [{ id: "b", label: " Keep spacing ", completed: true }],
  };
  const result = save_edit(saved, draft);
  expect(result).toEqual({ ok: true, saved: draft });
  for (const item of draft.items) item.label = "Later edit";
  if (!result.ok) throw new Error("Expected a valid save");
  expect(result.saved.items).toEqual([
    { id: "b", label: " Keep spacing ", completed: true },
  ]);
  expect(saved).toEqual(shipment());
});

test("a blank name has a structured validation error", () => {
  const saved = shipment();
  expect(save_edit(saved, { ...shipment(), name: " \t\n " })).toEqual({
    ok: false, error: { code: "blank_name", path: "name" },
  });
  expect(saved).toEqual(shipment());
});

test("an empty checklist has a structured validation error", () => {
  expect(save_edit(shipment(), { name: "Van", items: [] })).toEqual({
    ok: false, error: { code: "empty_items", path: "items" },
  });
});

test("a blank label reports its item path", () => {
  const draft = shipment();
  draft.items.push({ id: "photo", label: " \n ", completed: false });
  expect(save_edit(shipment(), draft)).toEqual({
    ok: false, error: { code: "blank_label", path: "items[2].label" },
  });
});

test("duplicate stable IDs are rejected without changing either argument", () => {
  const saved = shipment();
  const draft = {
    name: "Dispatch",
    items: [
      { id: "x", label: "First", completed: false },
      { id: "x", label: "Second", completed: true },
    ],
  };
  const before = JSON.stringify(draft);
  expect(save_edit(saved, draft)).toEqual({
    ok: false, error: { code: "duplicate_id", path: "items[1].id" },
  });
  expect(JSON.stringify(draft)).toBe(before);
  expect(saved).toEqual(shipment());
});

test("saving retains the caller's item order and completion flags", () => {
  const draft = {
    name: "Checks",
    items: [
      { id: "z", label: "Last alphabetically", completed: true },
      { id: "a", label: "First alphabetically", completed: false },
    ],
  };
  expect(save_edit(shipment(), draft)).toEqual({ ok: true, saved: draft });
});
