export interface ChecklistItem {
  id: string;
  label: string;
  completed: boolean;
}

export interface Checklist {
  name: string;
  items: ChecklistItem[];
}

export type SaveError =
  | { code: "blank_name"; path: "name" }
  | { code: "empty_items"; path: "items" }
  | { code: "blank_label"; path: string }
  | { code: "duplicate_id"; path: string };

export type SaveResult =
  | { ok: true; saved: Checklist }
  | { ok: false; error: SaveError };

export function begin_edit(saved: Checklist): Checklist {
  return { ...saved };
}

export function cancel_edit(_draft: Checklist): null {
  return null;
}

export function save_edit(_saved: Checklist, draft: Checklist): SaveResult {
  if (!draft.name.trim()) {
    return { ok: false, error: { code: "blank_name", path: "name" } };
  }
  if (draft.items.length === 0) {
    return { ok: false, error: { code: "empty_items", path: "items" } };
  }
  const seen = new Set<string>();
  for (const [index, item] of draft.items.entries()) {
    if (!item.label.trim()) {
      return {
        ok: false,
        error: { code: "blank_label", path: `items[${index}].label` },
      };
    }
    if (seen.has(item.id)) {
      return {
        ok: false,
        error: { code: "duplicate_id", path: `items[${index}].id` },
      };
    }
    seen.add(item.id);
  }
  return { ok: true, saved: { ...draft, items: [...draft.items] } };
}
