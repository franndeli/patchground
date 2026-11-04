# Cancelling an edit still changes the shipment checklist

The dispatch team edits a saved shipment checklist before a truck leaves. They report
that changing an item and then pressing Cancel sometimes changes the saved checklist.
A second report says that an old draft can change a checklist even after Save.

Repair the framework-free editing model in `src/checklist.ts`. Keep its exported
functions and result shapes. Add a regression check under `tests/`.

## Public API

`Checklist` has a `name: string` and ordered `items: ChecklistItem[]`.
Each item has `id: string`, `label: string` and `completed: boolean`.
Inputs have these TypeScript shapes already; parsing arbitrary external data is out of scope.

- `begin_edit(saved: Checklist): Checklist` returns an independent mutable draft.
  Changing its name, nested labels or completion flags, adding or removing items must
  not change saved state. Changes to saved state must not affect the draft either.
  Separate drafts of the same saved checklist must also be independent.
- `cancel_edit(draft: Checklist): null` returns null so the caller can discard its
  draft reference. It does not mutate the draft or saved state. The caller keeps the
  saved value; cancellation is not an undo operation on a shared object.
- `save_edit(saved: Checklist, draft: Checklist): SaveResult` does not mutate either
  argument. On success it returns `{ ok: true, saved: Checklist }`, an independent
  saved value containing the draft contents. Later edits to either input must not
  affect that value, nor may edits to the returned value affect either input.

Save preserves names and labels exactly as provided, stable item IDs, item order and
completion flags. Trimming is for validation only. No ID generation or sorting is needed.

## Validation contract

On failure return `{ ok: false, error: { code, path } }`; leave both arguments unchanged.
Return the first problem in the following order:

1. A whitespace-only or empty name: `code: "blank_name", path: "name"`.
2. An empty item list: `code: "empty_items", path: "items"`.
3. Visit items in order. A whitespace-only or empty label at index N:
   `code: "blank_label", path: "items[N].label"`.
   Otherwise an ID already seen earlier (exact string equality):
   `code: "duplicate_id", path: "items[N].id"`.

An invalid draft can be corrected and saved again. Repeated edit/save/cancel sessions
must retain the same independence guarantees.

## Scope and checks

This is an in-memory ownership bug, not a persistence or UI task. Do not add a backend,
DOM, browser framework, cloning library or dependency. Keep the container recipe and runner
unchanged. Use `pgnd check` in a session; all challenge commands run in Docker.
The visible checks cover saving, cancellation and validation. Hidden checks vary only
these documented behaviors and inputs.

This original exercise was AI-generated; difficulty and the 30-minute timebox are
provisional author estimates, not human calibration or an employer endorsement.
