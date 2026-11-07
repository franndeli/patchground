# Nobody can reuse the monthly sales totals

**Reported by:** finance engineering and the analytics team
**Component:** `reports`

## Symptom

Two teams want the numbers in the monthly sales report without the report:

1. Analytics receives sales from an event stream, not from the shop's SQLite database. They want
   the same refund and netting rules, but `reports/report.py` only works on a database file.
2. Finance wants a CSV next to the text report. Today the totals are computed inside the loop
   that pads the text columns, so a second format means copying the arithmetic.

The tests are slow and awkward for the same reason: every case needs a SQLite file.

## Reproduction

Open `src/reports/report.py`. `monthly_report(db_path, month)` validates the month, runs SQL,
nets refunds per SKU, sorts, and formats fixed-width text in one function.

## Expected

Split the module into three layers with dependencies that point inwards:

- `src/reports/domain.py`: frozen dataclasses `Sale(sku, quantity, unit_cents)`,
  `ProductLine(sku, net_cents)` and `MonthlySummary(month, lines, refunds_cents, total_cents)`
  where `lines` is a tuple of `ProductLine`, plus `summarize(month, sales) -> MonthlySummary`.
  `summarize` decides the order of `lines` (net descending, then SKU, as the report prints them)
  and raises `ValueError` for a malformed month. Importing the domain loads nothing from SQLite,
  storage, presentation or `report.py`, directly or indirectly.
- `src/reports/storage.py`: `SqliteSales(db_path).for_month(month)` returns that month's `Sale`
  values in insertion order. Importing it loads nothing from presentation.
- `src/reports/text.py`: `render(summary) -> str` produces today's text from any
  `MonthlySummary`. Importing it loads neither SQLite nor storage.
- `src/reports/report.py`: `monthly_report(db_path, month)` keeps its signature and output
  exactly. It only composes the layers. No SQL and no `sqlite3` import there.

## Notes

- This is an architecture change: the report's output must not change. The visible tests pin it.
- Add a test that exercises the netting rules through `summarize` with in-memory `Sale` values.
- CSV export itself is out of scope. Make it a small change for whoever writes it next.
- Run `pgnd check` from the session workspace to check your changes in Docker.
- You may use your own editor and AI tools. The goal is a module whose layers are explicit, not
  merely tests that pass.
