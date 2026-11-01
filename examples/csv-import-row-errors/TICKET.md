# Let the stock importer report bad rows instead of stopping at the first one

**Reported by:** warehouse operations
**Component:** `stockimport`

## Background

`import_inventory(text)` reads the nightly stock feed (`sku,quantity,unit_price`) and returns a list
of `Item`. It stops with `ImportFailed` at the first problem, so a feed with many bad rows takes many
re-uploads to fix. The feed data is synthetic in this exercise.

## Request

Add a non-strict mode that returns every valid item together with one error per rejected row. The
default behavior must not change.

### Public API

```python
import_inventory(text: str, *, strict: bool = True) -> list[Item] | ImportResult
```

- `strict=True` (the default) returns `list[Item]` exactly as today.
- `strict=False` returns `ImportResult(items: list[Item], errors: list[RowError])`.
- `strict` is keyword-only. `Item`, `RowError`, `ImportResult` and `ImportFailed` already exist in
  `stockimport/models.py` and are exported from `stockimport`; keep their fields and names.
- `Item(sku: str, quantity: int, unit_price_cents: int)`.
- `RowError(line: int, column: str | None, code: str, message: str)`. `message` is free human text
  and is not part of the contract.
- `ImportFailed` subclasses `ValueError`, carries the `RowError` as `.error`, and its text is
  `"line <line>: <message>"`.

### Input format and line numbers

The input is a string. The first physical line is the header; the rest are records. A quoted field
may contain line breaks, so a record can span several physical lines. Line numbers are 1-based
physical lines of the text (header = line 1). A record's line is the physical line **where it
starts**, and the next record's line counts every physical line before it.

### Rules

1. **Header.** The first record must be exactly `sku`, `quantity`, `unit_price` (case-sensitive, in
   that order, nothing else). Otherwise, including empty text or a blank first line, the import
   raises `ImportFailed` with `RowError(line=1, column=None, code="bad_header", ...)`, in both modes.
2. **Malformed CSV.** Only two syntax problems are recognized after the header: text other than a
   comma or line end right after a closing quote, and a quoted field never closed before the end of
   the text. Either raises `ImportFailed` with `code="malformed_csv"`, `column=None` and `line` the
   starting line of the record that contains the problem, in both modes. Non-strict mode returns no
   partial result in this case. Strict mode still raises the first row error that appears earlier in
   the text, if there is one.
3. **Empty lines.** A physical line with no characters at all (outside a quoted field) is skipped
   and is not an error. It still counts toward line numbers. A line holding only spaces or `""` is a
   record and is judged by rule 5.
4. **One error per row.** A rejected row produces exactly one `RowError`, for the first check below
   that fails. Fields are never trimmed.
5. **Checks, in this order**
   1. `wrong_field_count` (column `None`): the record does not have exactly 3 fields.
   2. `invalid_sku` (column `"sku"`): not one or more of `A-Z`, `0-9` and `-`.
   3. `duplicate_sku` (column `"sku"`): an earlier row in the same text was accepted with this sku.
   4. `invalid_quantity` (column `"quantity"`): not one or more ASCII digits `0-9`. Leading zeros are
      fine (`"007"` is 7). No sign, no spaces, no decimals, no exponent.
   5. `invalid_price` (column `"unit_price"`): not ASCII digits optionally followed by `.` and one
      or two ASCII digits (`"12"`, `"12.5"`, `"12.50"`, `"0.29"` are valid; `".5"`, `"5."`, `"12.345"`,
      `"-1"`, `"1e3"`, `"1,000.00"` are not).
6. **Cents.** `unit_price_cents` is the exact decimal amount times 100, as an `int`, computed
   without floating point: `"12"` → 1200, `"12.5"` → 1250, `"0.29"` → 29, `"19.99"` → 1999.
7. **Duplicates.** The first accepted row for a sku wins and its `Item` is never changed. A row
   rejected for any reason does not reserve its sku, so a later valid row with the same sku is
   accepted. A `duplicate_sku` row is itself rejected.
8. **Order.** `items` are in file order. `errors` are in file order (ascending `line`).
9. **Strict mode** raises `ImportFailed` for the first error in file order that the non-strict mode
   would report (rules 1–5 and 7 apply identically); it never reports a later error instead.
10. **Nothing accepted.** A text with a valid header and no valid rows gives `items == []` in
    non-strict mode.

## Example

```text
sku,quantity,unit_price
A-1,5,19.99
A-2,x,1.00
B-1,2,0.29

A-1,9,1.00
```

`import_inventory(text, strict=False)` returns items `A-1` (5 × 1999) and `B-1` (2 × 29), and errors
`(line=3, column="quantity", code="invalid_quantity")` and `(line=6, column="sku", code="duplicate_sku")`.
`import_inventory(text)` raises `ImportFailed` for line 3.

## Notes

- Keep the single-purpose importer in `importer.py`; do not add dependencies.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- Add tests for the behavior you implement and keep strict mode unchanged.
- You may use your own editor and AI tools. The goal is to build and explain a precise change, not
  only to make the listed cases pass.
